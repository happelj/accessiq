from .mock import ConnectorSimulationMode, MockIdentityConnector


class FinanceConnector(MockIdentityConnector):
    def __init__(
        self,
        *,
        enabled: bool = True,
        simulation_mode: ConnectorSimulationMode = ConnectorSimulationMode.SUCCESS,
        failures_before_success: int = 0,
    ) -> None:
        super().__init__(
            name="finance",
            display_name="Finance",
            enabled=enabled,
            simulation_mode=simulation_mode,
            failures_before_success=failures_before_success,
        )
