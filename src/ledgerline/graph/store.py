"""Graph stores: Neo4j (production) and an in-memory twin (tests) with identical semantics."""

from __future__ import annotations

import json
from typing import Any, Protocol

from ledgerline.graph.models import Control, Coverage, Requirement, Vendor


class GraphStore(Protocol):
    def reset(self) -> None: ...
    def add_requirement(self, r: Requirement) -> None: ...
    def add_control(self, c: Control) -> None: ...
    def add_vendor(self, v: Vendor) -> None: ...
    def add_coverage(self, cov: Coverage) -> None: ...
    def requirements(self) -> list[Requirement]: ...
    def controls(self) -> list[Control]: ...
    def unsatisfied_requirements(self) -> list[tuple[Requirement, list[Coverage]]]: ...
    def stats(self) -> dict[str, int]: ...


class MemoryGraph:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.reqs: dict[str, Requirement] = {}
        self.ctrls: dict[str, Control] = {}
        self.vendors: dict[str, Vendor] = {}
        self.cov: list[Coverage] = []

    def add_requirement(self, r: Requirement) -> None:
        self.reqs[r.id] = r

    def add_control(self, c: Control) -> None:
        self.ctrls[c.id] = c

    def add_vendor(self, v: Vendor) -> None:
        self.vendors[v.id] = v

    def add_coverage(self, cov: Coverage) -> None:
        self.cov.append(cov)

    def requirements(self) -> list[Requirement]:
        return list(self.reqs.values())

    def controls(self) -> list[Control]:
        return list(self.ctrls.values())

    def unsatisfied_requirements(self) -> list[tuple[Requirement, list[Coverage]]]:
        out = []
        for r in self.reqs.values():
            if not r.applies:
                continue
            covs = [c for c in self.cov if c.requirement_id == r.id]
            if not any(c.status == "satisfied" for c in covs):
                out.append((r, covs))
        return out

    def stats(self) -> dict[str, int]:
        return {
            "requirements": len(self.reqs),
            "controls": len(self.ctrls),
            "vendors": len(self.vendors),
            "coverage_edges": len(self.cov),
        }


class Neo4jGraph:
    """Every node and edge stores its source document and clause/page."""

    def __init__(self, uri: str, user: str, password: str) -> None:
        from neo4j import GraphDatabase

        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        self.driver.close()

    def q(self, cypher: str, **params: Any) -> list[dict[str, Any]]:
        records, _, _ = self.driver.execute_query(cypher, params)
        return [r.data() for r in records]

    def reset(self) -> None:
        self.q("MATCH (n) DETACH DELETE n")
        for label in ("Requirement", "Control", "Vendor", "Process", "Role", "Topic", "Document"):
            self.q(f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE")

    def _doc(self, prov: dict[str, Any]) -> None:
        self.q("MERGE (:Document {id: $doc_id})", doc_id=prov["doc_id"])

    def add_requirement(self, r: Requirement) -> None:
        p = r.prov.model_dump()
        self._doc(p)
        self.q(
            """
            MERGE (n:Requirement {id: $id})
            SET n.text = $text, n.actor = $actor, n.condition = $condition, n.topics = $topics,
                n.applies = $applies, n.kind = $kind, n.doc_id = $p.doc_id,
                n.clause = $p.clause, n.page = $p.page, n.chunk_id = $p.chunk_id,
                n.model = $p.extraction_model, n.cite = $cite
            WITH n MATCH (d:Document {id: $p.doc_id})
            MERGE (n)-[:FROM {clause: coalesce($p.clause, ''), page: coalesce($p.page, -1)}]->(d)
            WITH n UNWIND $topics AS t MERGE (tp:Topic {id: t}) MERGE (n)-[:ABOUT]->(tp)""",
            id=r.id,
            text=r.text,
            actor=r.actor,
            condition=r.condition,
            topics=r.topics,
            applies=r.applies,
            kind=r.kind,
            p=p,
            cite=r.prov.cite(),
        )

    def add_control(self, c: Control) -> None:
        p = c.prov.model_dump()
        self._doc(p)
        self.q(
            """
            MERGE (n:Control {id: $id})
            SET n.text = $text, n.process = $process, n.owner_role = $owner,
                n.type = $type, n.parameters = $params, n.topics = $topics,
                n.doc_id = $p.doc_id, n.section = $p.section, n.page = $p.page,
                n.chunk_id = $p.chunk_id, n.model = $p.extraction_model, n.cite = $cite
            MERGE (pr:Process {id: $process}) MERGE (pr)-[:HAS_CONTROL]->(n)
            MERGE (ro:Role {id: $owner}) MERGE (ro)-[:PERFORMS]->(pr)
            WITH n MATCH (d:Document {id: $p.doc_id})
            MERGE (n)-[:FROM {section: $p.section, page: coalesce($p.page, -1)}]->(d)
            WITH n UNWIND $topics AS t MERGE (tp:Topic {id: t}) MERGE (n)-[:ABOUT]->(tp)""",
            id=c.id,
            text=c.text,
            process=c.process,
            owner=c.owner_role,
            type=c.control_type,
            params=c.parameters,
            topics=c.topics,
            p=p,
            cite=c.prov.cite(),
        )

    def add_vendor(self, v: Vendor) -> None:
        p = v.prov.model_dump()
        self._doc(p)
        self.q(
            """
            MERGE (n:Vendor {id: $id}) SET n.name = $name, n.tier = $tier,
                n.doc_id = $p.doc_id, n.chunk_id = $p.chunk_id, n.cite = $cite
            WITH n UNWIND $processes AS pid
            MERGE (pr:Process {id: pid})
            MERGE (n)-[:SUPPORTS {doc_id: $p.doc_id}]->(pr)""",
            id=v.id,
            name=v.name,
            tier=v.tier,
            processes=v.processes,
            p=p,
            cite=v.prov.cite(),
        )

    def add_coverage(self, cov: Coverage) -> None:
        self.q(
            """
            MATCH (c:Control {id: $cid}), (r:Requirement {id: $rid})
            MERGE (c)-[s:SATISFIES]->(r)
            SET s.status = $status, s.rationale = $rationale, s.model = $model""",
            cid=cov.control_id,
            rid=cov.requirement_id,
            status=cov.status,
            rationale=cov.rationale,
            model=cov.model,
        )

    def _req(self, row: dict[str, Any]) -> Requirement:
        from ledgerline.graph.models import Provenance

        n = row["r"]
        return Requirement(
            id=n["id"],
            text=n["text"],
            actor=n["actor"],
            condition=n.get("condition") or "",
            topics=n["topics"],
            applies=n["applies"],
            kind=n["kind"],
            prov=Provenance(
                doc_id=n["doc_id"],
                chunk_id=n["chunk_id"],
                clause=n.get("clause"),
                page=n.get("page"),
                extraction_model=n.get("model") or "",
            ),
        )

    def requirements(self) -> list[Requirement]:
        return [self._req(r) for r in self.q("MATCH (r:Requirement) RETURN r")]

    def controls(self) -> list[Control]:
        from ledgerline.graph.models import Provenance

        out = []
        for row in self.q("MATCH (c:Control) RETURN c"):
            n = row["c"]
            out.append(
                Control(
                    id=n["id"],
                    text=n["text"],
                    process=n["process"],
                    owner_role=n["owner_role"],
                    control_type=n["type"],
                    parameters=n.get("parameters") or "",
                    topics=n["topics"],
                    prov=Provenance(
                        doc_id=n["doc_id"],
                        chunk_id=n["chunk_id"],
                        section=n.get("section") or "",
                        page=n.get("page"),
                    ),
                )
            )
        return out

    def unsatisfied_requirements(self) -> list[tuple[Requirement, list[Coverage]]]:
        """Gap query: applicable requirements with no SATISFIES edge of status 'satisfied'."""
        rows = self.q("""
            MATCH (r:Requirement {applies: true})
            WHERE NOT EXISTS { MATCH (:Control)-[s:SATISFIES]->(r) WHERE s.status = 'satisfied' }
            OPTIONAL MATCH (c:Control)-[s:SATISFIES]->(r)
            RETURN r, collect(CASE WHEN c IS NULL THEN null ELSE
                   {cid: c.id, status: s.status, rationale: s.rationale, model: s.model} END)
                   AS covs""")
        out = []
        for row in rows:
            covs = [
                Coverage(
                    control_id=c["cid"],
                    requirement_id=row["r"]["id"],
                    status=c["status"],
                    rationale=c["rationale"],
                    model=c["model"],
                )
                for c in row["covs"]
                if c
            ]
            out.append((self._req(row), covs))
        return out

    def stats(self) -> dict[str, int]:
        r = self.q("""
            RETURN COUNT { (:Requirement) } AS requirements, COUNT { (:Control) } AS controls,
                   COUNT { (:Vendor) } AS vendors, COUNT { ()-[:SATISFIES]->() } AS coverage_edges,
                   COUNT { (:Process) } AS processes, COUNT { (:Role) } AS roles""")[0]
        return {k: int(v) for k, v in r.items()}

    def export(self) -> str:
        return json.dumps(self.stats())
