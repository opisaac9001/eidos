"""Cached, checkpointed projections of Pathos's event stream shared by Life's services."""

from datetime import datetime

from eidos.application.consolidation import ConsolidationIndex
from eidos.application.memory import MemoryIndex
from eidos.domain.beliefs import BeliefState, project_beliefs
from eidos.domain.events import DomainEvent
from eidos.domain.finances import FinancialState, project_finances
from eidos.domain.household import HouseholdState, project_household
from eidos.domain.planning import PlanningState, project_planning
from eidos.domain.relationships import RelationshipState, project_relationships
from eidos.domain.state import PathosState
from eidos.domain.wellbeing import WellbeingState, project_wellbeing
from eidos.domain.world_catalog import WorldCatalog, project_world_catalog
from eidos.ports.event_store import (
    EventStore,
    MaterializedProjection,
    MaterializedProjectionStore,
    StateCheckpoint,
    StateCheckpointStore,
)
from eidos.ports.model_gateway import ModelGateway
from eidos.ports.town_signals import TownSignalSource


class LifeProjections:
    """The store, gateway and incrementally extended projection caches behind a Life.

    Every cache is keyed by (revision, last event id) so a projection built for a prefix of
    the stream is extended rather than rebuilt; materialized projections and state
    checkpoints let a restarted process resume without folding the whole life again.
    """

    def __init__(
        self,
        store: EventStore,
        gateway: ModelGateway,
        mode: str = "stand-in",
        town_signal_source: TownSignalSource | None = None,
        *,
        authored_scenario: bool = False,
    ) -> None:
        self.store = store
        self.gateway = gateway
        self.mode = mode
        self.town_signal_source = town_signal_source
        self.authored_scenario = authored_scenario
        self._memory_cache: tuple[int, str, MemoryIndex] | None = None
        self._world_catalog_cache: tuple[int, str, WorldCatalog] | None = None
        self._planning_cache: tuple[int, str, PlanningState] | None = None
        self._belief_cache: tuple[int, str, BeliefState] | None = None
        self._relationship_cache: tuple[int, str, RelationshipState] | None = None
        self._consolidation_cache: tuple[int, str, ConsolidationIndex] | None = None
        self._finance_cache: tuple[int, str, FinancialState] | None = None
        self._wellbeing_cache: tuple[int, str, WellbeingState] | None = None
        self._household_cache: tuple[int, str, HouseholdState] | None = None

    def history(self) -> list[DomainEvent]:
        return self.store.read("pathos")

    def _project_state(self, history: list[DomainEvent]) -> PathosState:
        state = PathosState()
        start = 0
        if isinstance(self.store, StateCheckpointStore):
            checkpoint = self.store.load_checkpoint("pathos", len(history))
            if checkpoint is not None:
                try:
                    raw = checkpoint.state
                    state = PathosState(
                        pathos_id=str(raw["pathos_id"]),
                        simulated_at=datetime.fromisoformat(str(raw["simulated_at"])),
                        location_id=str(raw["location_id"]),
                        energy=float(raw["energy"]),
                        valence=float(raw["valence"]),
                        arousal=float(raw["arousal"]),
                        rest=float(raw["rest"]),
                        connection=float(raw["connection"]),
                        curiosity=float(raw["curiosity"]),
                        mastery=float(raw["mastery"]),
                        hunger=float(raw.get("hunger", 0.15)),
                        awake=raw["awake"],
                    )
                    start = checkpoint.revision
                except (KeyError, TypeError, ValueError):
                    state = PathosState()
                    start = 0
        for event in history[start:]:
            state = state.apply(event)
        return state

    def _save_state_checkpoint(self, history: list[DomainEvent], state: PathosState) -> None:
        if not history or not isinstance(self.store, StateCheckpointStore):
            return
        self.store.save_checkpoint(
            StateCheckpoint(
                "pathos",
                len(history),
                str(history[-1].event_id),
                {
                    "pathos_id": state.pathos_id,
                    "simulated_at": state.simulated_at.isoformat(),
                    "location_id": state.location_id,
                    "energy": state.energy,
                    "valence": state.valence,
                    "arousal": state.arousal,
                    "rest": state.rest,
                    "connection": state.connection,
                    "curiosity": state.curiosity,
                    "mastery": state.mastery,
                    "hunger": state.hunger,
                    "awake": state.awake,
                },
            )
        )

    def _memory_index(self, history: list[DomainEvent]) -> MemoryIndex:
        if self._memory_cache is not None:
            revision, anchor, cached = self._memory_cache
            if revision <= len(history) and (
                revision == 0 or str(history[revision - 1].event_id) == anchor
            ):
                if revision == len(history):
                    return cached
                extended = MemoryIndex.build(history, base_index=cached)
                self._memory_cache = (len(history), str(history[-1].event_id), extended)
                return extended
        if isinstance(self.store, MaterializedProjectionStore):
            projection = self.store.load_projection("pathos", "memory-index", 1, len(history))
            if projection is not None:
                try:
                    index = MemoryIndex.build(
                        history,
                        materialized_state=projection.state,
                        materialized_revision=projection.revision,
                    )
                    self._memory_cache = (len(history), str(history[-1].event_id), index)
                    return index
                except (KeyError, TypeError, ValueError):
                    pass
        index = MemoryIndex.build(history)
        if history:
            self._memory_cache = (len(history), str(history[-1].event_id), index)
        return index

    def _world_catalog(self, history: list[DomainEvent]) -> WorldCatalog:
        if self._world_catalog_cache is not None:
            revision, anchor, catalog = self._world_catalog_cache
            if revision <= len(history) and (
                revision == 0 or str(history[revision - 1].event_id) == anchor
            ):
                for event in history[revision:]:
                    catalog = catalog.apply(event)
                anchor = str(history[-1].event_id) if history else ""
                self._world_catalog_cache = (len(history), anchor, catalog)
                return catalog
        catalog = project_world_catalog(history)
        anchor = str(history[-1].event_id) if history else ""
        self._world_catalog_cache = (len(history), anchor, catalog)
        return catalog

    def _finances(self, history: list[DomainEvent]) -> FinancialState:
        if self._finance_cache is not None:
            revision, anchor, finances = self._finance_cache
            if revision <= len(history) and (
                revision == 0 or str(history[revision - 1].event_id) == anchor
            ):
                for event in history[revision:]:
                    finances = finances.apply(event)
                anchor = str(history[-1].event_id) if history else ""
                self._finance_cache = (len(history), anchor, finances)
                return finances
        finances = project_finances(history)
        anchor = str(history[-1].event_id) if history else ""
        self._finance_cache = (len(history), anchor, finances)
        return finances

    def _wellbeing(self, history: list[DomainEvent]) -> WellbeingState:
        if self._wellbeing_cache is not None:
            revision, anchor, wellbeing = self._wellbeing_cache
            if revision <= len(history) and (
                revision == 0 or str(history[revision - 1].event_id) == anchor
            ):
                for event in history[revision:]:
                    wellbeing = wellbeing.apply(event)
                anchor = str(history[-1].event_id) if history else ""
                self._wellbeing_cache = (len(history), anchor, wellbeing)
                return wellbeing
        wellbeing = project_wellbeing(history)
        anchor = str(history[-1].event_id) if history else ""
        self._wellbeing_cache = (len(history), anchor, wellbeing)
        return wellbeing

    def _household(self, history: list[DomainEvent]) -> HouseholdState:
        if self._household_cache is not None:
            revision, anchor, household = self._household_cache
            if revision <= len(history) and (
                revision == 0 or str(history[revision - 1].event_id) == anchor
            ):
                for event in history[revision:]:
                    household = household.apply(event)
                anchor = str(history[-1].event_id) if history else ""
                self._household_cache = (len(history), anchor, household)
                return household
        household = project_household(history)
        anchor = str(history[-1].event_id) if history else ""
        self._household_cache = (len(history), anchor, household)
        return household

    def _planning(self, history: list[DomainEvent]) -> PlanningState:
        if self._planning_cache is not None:
            revision, anchor, planning = self._planning_cache
            if revision <= len(history) and (
                revision == 0 or str(history[revision - 1].event_id) == anchor
            ):
                for event in history[revision:]:
                    planning = planning.apply(event)
                anchor = str(history[-1].event_id) if history else ""
                self._planning_cache = (len(history), anchor, planning)
                return planning
        if isinstance(self.store, MaterializedProjectionStore):
            projection = self.store.load_projection("pathos", "planning", 1, len(history))
            if projection is not None:
                try:
                    planning = PlanningState.from_materialized_state(projection.state)
                    for event in history[projection.revision :]:
                        planning = planning.apply(event)
                    anchor = str(history[-1].event_id) if history else ""
                    self._planning_cache = (len(history), anchor, planning)
                    return planning
                except (KeyError, TypeError, ValueError):
                    pass
        planning = project_planning(history)
        anchor = str(history[-1].event_id) if history else ""
        self._planning_cache = (len(history), anchor, planning)
        return planning

    def _save_memory_index(self, history: list[DomainEvent]) -> None:
        if not history or not isinstance(self.store, MaterializedProjectionStore):
            return
        index = self._memory_index(history)
        self.store.save_projection(
            MaterializedProjection(
                "pathos",
                "memory-index",
                1,
                len(history),
                str(history[-1].event_id),
                index.materialized_state(),
            )
        )

    def _save_planning(self, history: list[DomainEvent]) -> None:
        if not history or not isinstance(self.store, MaterializedProjectionStore):
            return
        planning = self._planning(history)
        self.store.save_projection(
            MaterializedProjection(
                "pathos",
                "planning",
                1,
                len(history),
                str(history[-1].event_id),
                planning.materialized_state(),
            )
        )

    def _beliefs(self, history: list[DomainEvent]) -> BeliefState:
        if self._belief_cache is not None:
            revision, anchor, beliefs = self._belief_cache
            if revision <= len(history) and (
                revision == 0 or str(history[revision - 1].event_id) == anchor
            ):
                for event in history[revision:]:
                    beliefs = beliefs.apply(event)
                anchor = str(history[-1].event_id) if history else ""
                self._belief_cache = (len(history), anchor, beliefs)
                return beliefs
        if isinstance(self.store, MaterializedProjectionStore):
            projection = self.store.load_projection("pathos", "beliefs", 1, len(history))
            if projection is not None:
                try:
                    beliefs = BeliefState.from_materialized_state(projection.state)
                    for event in history[projection.revision :]:
                        beliefs = beliefs.apply(event)
                    anchor = str(history[-1].event_id) if history else ""
                    self._belief_cache = (len(history), anchor, beliefs)
                    return beliefs
                except (KeyError, TypeError, ValueError):
                    pass
        beliefs = project_beliefs(history)
        anchor = str(history[-1].event_id) if history else ""
        self._belief_cache = (len(history), anchor, beliefs)
        return beliefs

    def _save_beliefs(self, history: list[DomainEvent]) -> None:
        if not history or not isinstance(self.store, MaterializedProjectionStore):
            return
        beliefs = self._beliefs(history)
        self.store.save_projection(
            MaterializedProjection(
                "pathos",
                "beliefs",
                1,
                len(history),
                str(history[-1].event_id),
                beliefs.materialized_state(),
            )
        )

    def _relationships(self, history: list[DomainEvent]) -> RelationshipState:
        if self._relationship_cache is not None:
            revision, anchor, relationships = self._relationship_cache
            if revision <= len(history) and (
                revision == 0 or str(history[revision - 1].event_id) == anchor
            ):
                for event in history[revision:]:
                    relationships = relationships.apply(event)
                anchor = str(history[-1].event_id) if history else ""
                self._relationship_cache = (len(history), anchor, relationships)
                return relationships
        if isinstance(self.store, MaterializedProjectionStore):
            projection = self.store.load_projection("pathos", "relationships", 1, len(history))
            if projection is not None:
                try:
                    relationships = RelationshipState.from_materialized_state(projection.state)
                    for event in history[projection.revision :]:
                        relationships = relationships.apply(event)
                    anchor = str(history[-1].event_id) if history else ""
                    self._relationship_cache = (len(history), anchor, relationships)
                    return relationships
                except (KeyError, TypeError, ValueError):
                    pass
        relationships = project_relationships(history)
        anchor = str(history[-1].event_id) if history else ""
        self._relationship_cache = (len(history), anchor, relationships)
        return relationships

    def _save_relationships(self, history: list[DomainEvent]) -> None:
        if not history or not isinstance(self.store, MaterializedProjectionStore):
            return
        relationships = self._relationships(history)
        self.store.save_projection(
            MaterializedProjection(
                "pathos",
                "relationships",
                1,
                len(history),
                str(history[-1].event_id),
                relationships.materialized_state(),
            )
        )

    def _consolidation_index(self, history: list[DomainEvent]) -> ConsolidationIndex:
        if self._consolidation_cache is not None:
            revision, anchor, index = self._consolidation_cache
            if revision <= len(history) and (
                revision == 0 or str(history[revision - 1].event_id) == anchor
            ):
                extended = ConsolidationIndex.build(history, base_index=index)
                anchor = str(history[-1].event_id) if history else ""
                self._consolidation_cache = (len(history), anchor, extended)
                return extended
        if isinstance(self.store, MaterializedProjectionStore):
            projection = self.store.load_projection(
                "pathos", "consolidation-index", 1, len(history)
            )
            if projection is not None:
                try:
                    index = ConsolidationIndex.build(
                        history,
                        materialized_state=projection.state,
                        materialized_revision=projection.revision,
                    )
                    anchor = str(history[-1].event_id) if history else ""
                    self._consolidation_cache = (len(history), anchor, index)
                    return index
                except (KeyError, TypeError, ValueError):
                    pass
        index = ConsolidationIndex.build(history)
        anchor = str(history[-1].event_id) if history else ""
        self._consolidation_cache = (len(history), anchor, index)
        return index

    def _save_consolidation_index(self, history: list[DomainEvent]) -> None:
        if not history or not isinstance(self.store, MaterializedProjectionStore):
            return
        index = self._consolidation_index(history)
        self.store.save_projection(
            MaterializedProjection(
                "pathos",
                "consolidation-index",
                1,
                len(history),
                str(history[-1].event_id),
                index.materialized_state(),
            )
        )

    @staticmethod
    def project(history: list[DomainEvent]) -> PathosState:
        state = PathosState()
        for event in history:
            state = state.apply(event)
        return state
