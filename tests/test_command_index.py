"""命令索引：隐藏的子命令组必须可被发现"""


def test_index_exposes_hidden_groups():
    from app.commands.index import collect_index

    data = collect_index()
    names = {g["name"] for g in data["groups"]}

    for expected in ("ai", "paper", "backtest", "market", "digest", "alert"):
        assert expected in names


def test_index_lists_subcommands_for_each_group():
    from app.commands.index import collect_index

    for group in collect_index()["groups"]:
        assert group["commands"], f"{group['name']} 没有列出任何子命令"
        assert group["example"].startswith("stock-ai")
        assert group["description"]


def test_index_contains_new_top_level_commands():
    from app.commands.index import collect_index

    names = set(collect_index()["top_level"])
    for expected in ("commands", "cmd", "q", "report", "rp", "bt-pf"):
        assert expected in names


def test_frozen_order_group_is_not_exposed():
    from app.commands.index import collect_index

    names = {g["name"] for g in collect_index()["groups"]}
    assert "order" not in names
