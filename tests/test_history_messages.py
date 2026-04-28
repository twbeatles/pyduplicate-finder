from src.ui.history_messages import parse_structured_history_message


def test_parse_structured_history_message_extracts_known_fields():
    fields = parse_structured_history_message(
        "partial;missing_folders:2;export_failed:csv,json;watch_events:5"
    )

    assert fields["missing_folders"] == "2"
    assert fields["export_failed"] == "csv,json"
    assert fields["watch_events"] == "5"


def test_parse_structured_history_message_ignores_unknown_fields():
    fields = parse_structured_history_message("completed;other:value")

    assert fields["missing_folders"] == ""
    assert fields["export_failed"] == ""
    assert fields["watch_events"] == ""
