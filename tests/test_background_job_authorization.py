from unittest.mock import Mock, patch

from backend.app.background_jobs import JOB_FINAL_REPORT, enqueue_job, get_latest_job


PROJECT_ID = "10000000-0000-0000-0000-000000000001"
USER_ID = "20000000-0000-0000-0000-000000000002"
JOB_ID = "30000000-0000-0000-0000-000000000003"


def _connection(fetchone_values):
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    cursor.fetchone.side_effect = list(fetchone_values)
    connection.cursor.return_value = cursor
    return connection, cursor


@patch("backend.app.background_jobs.require_project_access")
@patch("backend.app.background_jobs.get_connection")
def test_enqueue_records_authorized_requester(get_connection, authorize):
    connection, cursor = _connection(
        [
            {"archived_at": None},
            {
                "id": JOB_ID,
                "project_id": PROJECT_ID,
                "requested_by_user_id": USER_ID,
                "job_type": JOB_FINAL_REPORT,
                "status": "queued",
            },
        ]
    )
    get_connection.return_value = connection
    authorize.return_value.user.id = USER_ID

    job, created = enqueue_job(PROJECT_ID, JOB_FINAL_REPORT)

    assert created is True
    assert job["id"] == JOB_ID
    authorize.assert_called_once_with(
        PROJECT_ID,
        "editor",
        connection_factory=get_connection,
    )
    insert_sql, insert_params = cursor.execute.call_args_list[1].args
    assert "requested_by_user_id" in insert_sql
    assert insert_params[1] == USER_ID
    connection.commit.assert_called_once()


@patch("backend.app.background_jobs.require_project_access")
@patch("backend.app.background_jobs.get_connection")
def test_latest_job_requires_at_least_viewer_access(get_connection, authorize):
    connection, _cursor = _connection([None])
    get_connection.return_value = connection

    assert get_latest_job(PROJECT_ID, JOB_FINAL_REPORT) is None

    authorize.assert_called_once_with(
        PROJECT_ID,
        "viewer",
        connection_factory=get_connection,
    )
