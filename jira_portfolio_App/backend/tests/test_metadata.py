from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.metadata import MetadataService
from app.models import JiraField, JiraFieldContext, JiraProject


class StubJira:
    field_name = "Delivery confidence"

    async def projects(self):
        return [{"id": "100", "key": "PORT", "name": "Portfolio"}]

    async def fields(self):
        return [
            {
                "id": "customfield_123",
                "name": self.field_name,
                "custom": True,
                "searchable": True,
                "schema": {"type": "option", "customId": 123},
            }
        ]

    async def issue_types(self):
        return [{"id": "9", "name": "Initiative", "hierarchyLevel": 2}]

    async def statuses(self):
        return [{"id": "1", "name": "Open", "statusCategory": {"key": "new"}}]

    async def field_contexts(self, field_id):
        assert field_id == "customfield_123"
        return [{"id": "20", "projectIds": ["100"], "issueTypeIds": ["9"]}]

    async def context_options(self, field_id, context_id):
        return [{"id": "1", "value": "Green"}]


async def test_refresh_persists_dynamic_metadata_and_rename() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    jira = StubJira()
    with Session(engine, expire_on_commit=False) as db:
        first = await MetadataService(db, jira).refresh()  # type: ignore[arg-type]
        assert first.status == "succeeded"
        field = db.scalar(select(JiraField).where(JiraField.jira_field_id == "customfield_123"))
        assert field and field.name == "Delivery confidence"
        field.selected = True
        db.commit()
        jira.field_name = "Portfolio confidence"
        await MetadataService(db, jira).refresh()  # type: ignore[arg-type]
        fields = list(db.scalars(select(JiraField)))
        assert len(fields) == 1
        assert fields[0].name == "Portfolio confidence"
        assert fields[0].selected is True
        assert db.scalar(select(JiraProject)).active is False
        context = db.scalar(select(JiraFieldContext))
        assert context.options_json == [{"id": "1", "value": "Green"}]
