import igp2 as ip
import numpy as np
from typing import Optional

from igp2.agents.agent import Agent


class TrajectoryAgent(Agent):
    """ Agent that follows a predefined trajectory. """

    def __init__(self,
                 agent_id: int,
                 initial_state: ip.AgentState,
                 goal: ip.Goal = None,
                 fps: int = 20,
                 open_loop: bool = False):
        """ Initialise new trajectory-following agent.

        Args:
            agent_id: ID of the agent
            initial_state: Starting state of the agent
            goal: Optional final goal of the vehicle
            fps: Execution rate of the environment simulation
            open_loop: Whether to use open-loop predictions directly instead of closed-loop control
        """
        super().__init__(agent_id, initial_state, goal, fps)

        self._t = 0
        self._open_loop = open_loop
        self._trajectory = None
        self._maneuver_config = None
        self._maneuver = None
        self._init_vehicle()

    def done(self, observation: ip.Observation) -> bool:
        if self.open_loop:
            done = self._t == len(self._trajectory.path) - 1
        else:
            dist = np.linalg.norm(self._trajectory.path[-1] - observation.frame[self.agent_id].position)
            done = dist < 1.0  # arbitrary
        return done

    def next_action(self, observation: ip.Observation) -> Optional[ip.Action]:
        """ Calculate next action based on trajectory and optionally steps
        the current state of the agent forward. """
        assert self._trajectory is not None, f"Trajectory of Agent {self.agent_id} was None!"
        if self.done(observation):
            return None

        self._t += 1

        if self.open_loop:
            action = ip.Action(self._trajectory.acceleration[self._t],
                               self._trajectory.angular_velocity[self._t])
        else:
            if self._maneuver is None:
                self._maneuver_config = ip.ManeuverConfig({'type': 'trajectory',
                                                           'termination_point': self._trajectory.path[-1]})
                self._maneuver = ip.TrajectoryManeuverCL(self._maneuver_config, self.agent_id, observation.frame,
                                                         observation.scenario_map, self._trajectory)
            action = self._maneuver.next_action(observation)

        return action

    def next_state(self, observation: ip.Observation) -> ip.AgentState:
        """ Calculate next action based on trajectory, set appropriate fields in vehicle
        and returns the next agent state. """
        assert self._trajectory is not None, f"Trajectory of Agent {self.agent_id} was None!"

        if len(self._trajectory.path) > 2000:
            self._trajectory = self._trajectory.slice(0,2000)
        if self.done(observation):
            return self.state

        action = self.next_action(observation)

        if self.open_loop:
            new_state = ip.AgentState(
                self._t,
                self._trajectory.path[self._t],
                self._trajectory.velocity[self._t],
                self._trajectory.acceleration[self._t],
                self._trajectory.heading[self._t]
            )
        else:
            new_state = None

        self.vehicle.execute_action(action, new_state)
        return self.vehicle.get_state(observation.frame[self.agent_id].time + 1)

    def set_trajectory(self, new_trajectory: ip.Trajectory):
        """ Override current trajectory of the vehicle and resample to match execution frequency of the environment.
        If the trajectory given is empty or None, then the vehicle will stay in place for 10 seconds. """

        fps = self._vehicle.fps
        if not new_trajectory:
            self._trajectory = ip.VelocityTrajectory(
                np.repeat([self._initial_state.position], 10 * fps, axis=0),
                np.zeros(10 * fps),
                np.repeat(self._initial_state.heading, 10 * fps),
                np.arange(0.0, 10 * fps, 1 / fps)
            )
            if len(self._trajectory.path) > 1000:
                self._trajectory = self._trajectory.slice(0, 1000)

        elif isinstance(new_trajectory, ip.StateTrajectory) and new_trajectory.fps == fps:
            self._trajectory = ip.VelocityTrajectory(
                new_trajectory.path, new_trajectory.velocity,
                new_trajectory.heading, new_trajectory.timesteps)
            if len(new_trajectory.path) > 1000:
                new_trajectory = new_trajectory.slice(0, 1000)

        else:
            num_frames = np.ceil(new_trajectory.duration * fps)
            ts = new_trajectory.times
            points = np.linspace(ts[0], ts[-1], int(num_frames))

            xs_r = np.interp(points, ts, new_trajectory.path[:, 0])
            ys_r = np.interp(points, ts, new_trajectory.path[:, 1])
            v_r = np.interp(points, ts, new_trajectory.velocity)
            path = np.c_[xs_r, ys_r]
            self._trajectory = ip.VelocityTrajectory(path, v_r)

    def reset(self):
        super(TrajectoryAgent, self).reset()
        self._t = 0
        self._trajectory = None
        self._maneuver_config = None
        self._maneuver = None
        self._init_vehicle()

    def _init_vehicle(self):
        """ Create vehicle object of this agent. """
        if self.open_loop:
            self._vehicle = ip.TrajectoryVehicle(self._initial_state, self.metadata, self._fps)
        else:
            self._vehicle = ip.KinematicVehicle(self._initial_state, self.metadata, self._fps)

    @property
    def trajectory(self) -> ip.Trajectory:
        """ Return the currently defined trajectory of the agent. """
        return self._trajectory

    @property
    def open_loop(self) -> bool:
        """ Whether to use open-loop predictions directly instead of closed-loop control. """
        return self._open_loop

    def parked(self, tol=1.0) -> bool:
        return np.linalg.norm(self.trajectory.path[0] - self.trajectory.path[-1]) < tol
