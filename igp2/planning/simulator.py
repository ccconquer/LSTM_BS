import igp2 as ip
import logging
from typing import Dict, List, Tuple
import matplotlib.pyplot as plt

from gui.tracks_import import calculate_rotated_bboxes

logger = logging.getLogger(__name__)


class Simulator:
    """ Lightweight environment simulator useful for rolling out scenarios in MCTS.

    One agent is designated as the ego vehicle, while the other agents follow predefined trajectories calculated
    during goal recognition. Simulation is performed at a given frequency with collision checking.
    """

    def __init__(self,
                 ego_id: int,
                 initial_frame: Dict[int, ip.AgentState],
                 metadata: Dict[int, ip.AgentMetadata],
                 scenario_map: ip.Map,
                 fps: int = 10,
                 open_loop_agents: bool = False,
                 t_max: int = 300):
        """Initialise new light-weight simulator with the given params.

        Args:
            ego_id: ID of the ego vehicle
            initial_frame: initial state of the environment
            metadata: metadata describing the agents in the environment
            scenario_map: current road layout
            fps: frame rate of simulation
            open_loop_agents: Whether non-ego agents follow open-loop control
            t_max: Maximum rollout time step length
        """
        assert ego_id in initial_frame, f"Ego ID {ego_id} is not in the initial frame!"
        assert ego_id in metadata, f"Ego ID {ego_id} not among given metadata!"

        self._scenario_map = scenario_map
        self._ego_id = ego_id
        self._initial_frame = initial_frame
        self._metadata = metadata
        self._fps = fps
        self._open_loop = open_loop_agents
        self._t_max = t_max
        self._agents = self._create_agents()

    def update_trajectory(self, agent_id: int, new_trajectory: ip.Trajectory):
        """ Update the predicted trajectory of the non-ego agent. Has no effect for ego or if agent_id not in agents

        Args:
            agent_id: ID of agent to update
            new_trajectory: new trajectory for agent
        """
        if agent_id in self._agents and agent_id != self._ego_id:
            self._agents[agent_id].set_trajectory(new_trajectory)

    def update_ego_action(self,
                          action: ip.MacroAction,
                          args: Dict,
                          frame: Dict[int, ip.AgentState]) -> ip.MacroAction:
        """ Update the current macro action of the ego vehicle.

        Args:
            action: new macro action to execute
            args: MA initialisation arguments
            frame: Current state of the environment

        Returns:
            The currently execute MA of the ego
        """
        observation = ip.Observation(frame, self._scenario_map)
        ma = self._agents[self._ego_id].update_macro_action(action, args, observation)
        return ma

    def update_ego_goal(self, goal: ip.Goal):
        """ Update the final goal of the ego vehicle.

        Args:
            goal: new goal to reach
        """
        self._agents[self._ego_id].update_goal(goal)

    def reset(self):
        """ Reset the internal states of the environment to initialisation defaults. """
        for agent_id, agent in self._agents.items():
            agent.reset()

    def run(self, start_frame: Dict[int, ip.AgentState], plot_rollout: bool = False) \
            -> Tuple[ip.StateTrajectory, Dict[int, ip.AgentState], bool, bool, List[ip.Agent]]:
        """ Execute current macro action of ego and forward the state of the environment with collision checking.

        Returns:
            A 5-tuple giving the new state of the environment, the final frame of the simulation,
            whether the ego has reached its goal, whether the ego is still alive, and if it has collided with another
            (possible multiple) agents and if so the colliding agents.
        """
        ego = self._agents[self._ego_id]
        current_observation = ip.Observation(start_frame, self._scenario_map)

        goal_reached = False
        collisions = []

        start_time = len(ego.trajectory_cl.states)
        t = 0
        while t < self._t_max and ego.alive and not goal_reached and not ego.done(current_observation):
            new_frame = {}

            # Update agent states
            for agent_id, agent in self._agents.items():
                if not agent.alive:
                    continue
                if agent.done(current_observation):
                    agent.alive = False
                    continue

                new_state = agent.next_state(current_observation)
                agent.trajectory_cl.add_state(new_state, reload_path=False)
                new_frame[agent_id] = new_state

                agent.alive = len(self._scenario_map.roads_at(new_state.position)) > 0

            current_observation = ip.Observation(new_frame, self._scenario_map)

            collisions = self._check_collisions(ego)
            if collisions:
                ego.alive = False
            else:
                goal_reached = ego.goal.reached(ego.state.position)

            if plot_rollout and t % 5 == 0:
                self.plot()
                plt.show()
            t += 1

        ego.trajectory_cl.calculate_path_and_velocity()
        driven_trajectory = ego.trajectory_cl.slice(start_time, start_time + t)
        return driven_trajectory, current_observation.frame, goal_reached, ego.alive, collisions

    def _create_agents(self) -> Dict[int, ip.Agent]:
        """ Initialise new agents. Each non-ego is a TrajectoryAgent, while the ego is a MacroAgent. """
        agents = {}
        for aid, state in self._initial_frame.items():
            if aid == self._ego_id:
                agents[aid] = ip.MacroAgent(aid, state, fps=self._fps)
            else:
                agents[aid] = ip.TrajectoryAgent(aid, state, fps=self._fps, open_loop=self._open_loop)
        return agents

    def _check_collisions(self, ego: ip.Agent) -> List[ip.Agent]:
        """ Check for collisions with the given vehicle in the environment. """
        colliding_agents = []
        for agent_id, agent in self._agents.items():
            if agent_id == ego.agent_id or not agent.alive:
                continue

            if agent.vehicle.overlaps(ego.vehicle):
                agent.alive = False
                colliding_agents.append(agent)

        return colliding_agents

    def plot(self, axis: plt.Axes = None) -> plt.Axes:
        """ Plot the current agents and the road layout for visualisation purposes.

        Args:
            axis: Axis to draw on
        """
        if axis is None:
            fig, axis = plt.subplots()

        color_map_ego = plt.cm.get_cmap('Reds')
        color_map_non_ego = plt.cm.get_cmap('Blues')
        color_ego = 'r'
        color_non_ego = 'b'
        color_bar_non_ego = None

        ip.plot_map(self._scenario_map, markings=True, ax=axis)
        for agent_id, agent in self._agents.items():
            if not agent.alive:
                continue

            if isinstance(agent, ip.MacroAgent):
                color = color_ego
                color_map = color_map_ego
                path = agent.current_macro.current_maneuver.trajectory.path
                velocity = agent.current_macro.current_maneuver.trajectory.velocity
            elif isinstance(agent, ip.TrajectoryAgent):
                color = color_non_ego
                color_map = color_map_non_ego
                path = agent.trajectory.path
                velocity = agent.trajectory.velocity

            vehicle = agent.vehicle
            bounding_box = calculate_rotated_bboxes(vehicle.center[0], vehicle.center[1],
                                                    vehicle.length, vehicle.width,
                                                    vehicle.heading)
            pol = plt.Polygon(bounding_box[0], color=color)
            axis.add_patch(pol)
            agent_plot = axis.scatter(path[:, 0], path[:, 1], c=velocity, cmap=color_map, vmin=-4, vmax=20, s=8)
            if isinstance(agent, ip.MacroAgent):
                plt.colorbar(agent_plot)
                plt.text(0, 0.1, 'Current Velocity: ' + str(agent.state.speed), horizontalalignment='left',
                         verticalalignment='bottom', transform=axis.transAxes)
                plt.text(0, 0.05, 'Current Macro Action: ' + agent.current_macro.__repr__(), horizontalalignment='left',
                         verticalalignment='bottom', transform=axis.transAxes)
                plt.text(0, 0, 'Current Maneuver: ' + agent.current_macro.current_maneuver.__repr__(),
                         horizontalalignment='left', verticalalignment='bottom', transform=axis.transAxes)
            elif isinstance(agent, ip.TrajectoryAgent) and color_bar_non_ego is None:
                color_bar_non_ego = plt.colorbar(agent_plot)
            plt.text(*agent.state.position, agent_id)
        return axis

    @property
    def ego_id(self) -> int:
        """ ID of the ego vehicle"""
        return self._ego_id

    @property
    def agents(self) -> Dict[int, ip.Agent]:
        """ Return current agents of the environment """
        return self._agents

    @property
    def initial_frame(self) -> Dict[int, ip.AgentState]:
        """ Return the initial state of the environment """
        return self._initial_frame

    @property
    def fps(self) -> int:
        """ Executing frame rate of the simulator"""
        return self._fps

    @property
    def metadata(self) -> Dict[int, ip.AgentMetadata]:
        """ Metadata of agents in the current frame """
        return self._metadata
