"""校准记录导入的回归测试：路由顺序、逐行反馈、幂等重试与指标对应。

运行：python3 -m pytest backend/tests/test_calibration_import.py
测试使用唯一编号前缀，互不依赖，可重复执行。
"""
from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def prefix() -> str:
    """每个用例独立的记录编号前缀，避免共享内存仓库里的相互影响。"""
    return f"T{uuid.uuid4().hex[:8].upper()}"


def upload(name: str, content: bytes) -> dict:
    response = client.post("/api/calibration/import", files={"file": (name, content, "text/csv")})
    assert response.status_code == 200
    return response.json()


def count_by_number(keyword: str) -> int:
    response = client.get("/api/calibration", params={"keyword": keyword})
    assert response.status_code == 200
    return int(response.json()["total"])


def test_export_route_not_shadowed_by_detail_route() -> None:
    """/export 固定路径不能被 /{entry_id} 吃掉：下载与详情都要可用。"""
    export = client.get("/api/calibration/export")
    assert export.status_code == 200
    assert export.json()["module"] == "calibration"
    detail = client.get("/api/calibration/1")
    assert detail.status_code == 200
    assert detail.json()["记录编号"]


def test_empty_file_and_header_only_file_are_rejected() -> None:
    empty = upload("empty.csv", b"")
    assert empty["ok"] is False
    assert "空" in empty["message"]

    header_only = upload("header.csv", "记录编号,仪器编号,校准机构\n".encode("utf-8"))
    assert header_only["ok"] is False
    assert "数据行" in header_only["message"]


def test_missing_required_header_is_rejected() -> None:
    body = upload("bad.csv", "仪器编号,校准机构\nI-1,机构A\n".encode("utf-8"))
    assert body["ok"] is False
    assert "记录编号" in body["message"]


def test_duplicate_rows_in_one_file_create_single_record() -> None:
    p = prefix()
    csv_text = (
        "记录编号,仪器编号,校准机构\n"
        f"{p}-1,INST-1,机构A\n"
        f"{p}-1,INST-1,机构A\n"
    )
    body = upload("dup.csv", csv_text.encode("utf-8"))
    summary = body["summary"]
    assert summary["created"] == 1
    assert summary["duplicated"] == 1
    dup = next(item for item in body["results"] if item["result"] == "重复")
    assert dup["row"] == 2 and "第 1 行" in dup["message"]
    assert count_by_number(f"{p}-1") == 1


def test_rows_missing_required_columns_fail_with_feedback() -> None:
    p = prefix()
    csv_text = (
        "记录编号,仪器编号,校准机构,校准日期\n"
        f"{p}-1,INST-1,,2026-09-26\n"
        ",INST-2,机构B,2026-09-26\n"
    )
    body = upload("missing.csv", csv_text.encode("utf-8"))
    summary = body["summary"]
    assert summary["failed"] == 2
    messages = [item["message"] for item in body["results"] if item["result"] == "失败"]
    assert any("校准机构" in message for message in messages)
    assert any("记录编号" in message for message in messages)
    # 缺列的行不能变成页面上看不见的残缺记录
    assert count_by_number(p) == 0


def test_reimport_is_idempotent_and_never_overwrites_with_blanks() -> None:
    p = prefix()
    first = f"记录编号,仪器编号,校准机构,校准日期\n{p}-1,INST-1,机构A,2026-09-01\n".encode("utf-8")
    assert upload("one.csv", first)["summary"]["created"] == 1

    # 中断后重试：同一文件再传，不产生新记录、不改动内容
    again = upload("one.csv", first)["summary"]
    assert again["created"] == 0 and again["unchanged"] == 1 and again["updated"] == 0

    # 空白字段一律保留原值，只有非空字段参与更新
    patch = f"记录编号,仪器编号,校准机构,校准日期\n{p}-1,,,2026-09-20\n".encode("utf-8")
    assert upload("patch.csv", patch)["summary"]["updated"] == 1
    record = client.get("/api/calibration", params={"keyword": f"{p}-1"}).json()["items"][0]
    assert record["仪器编号"] == "INST-1"
    assert record["校准机构"] == "机构A"
    assert record["校准日期"] == "2026-09-20"
    assert count_by_number(p) == 1


def test_json_import_and_export_round_trip() -> None:
    p = prefix()
    payload = json.dumps([{"记录编号": f"{p}-1", "仪器编号": "INST-1", "校准机构": "机构A"}]).encode("utf-8")
    assert upload("new.json", payload)["summary"]["created"] == 1

    # 导出的清单可以直接再导入：不重复、不丢失、不失败
    exported = client.get("/api/calibration/export").json()
    total_before = exported["total"]
    summary = upload("roundtrip.json", json.dumps(exported).encode("utf-8"))["summary"]
    assert summary["created"] == 0 and summary["failed"] == 0
    assert client.get("/api/calibration/export").json()["total"] == total_before


def test_stats_cards_match_filtered_list() -> None:
    """指标卡、列表、状态三者必须对应。"""
    p = prefix()
    upload("stat.csv", f"记录编号,仪器编号,校准机构\n{p}-1,INST-1,机构A\n".encode("utf-8"))
    entry_id = client.get("/api/calibration", params={"keyword": f"{p}-1"}).json()["items"][0]["id"]
    action = client.post(f"/api/calibration/{entry_id}/actions", json={"values": {"action": "标记合格"}})
    assert action.json()["ok"] is True

    cards = {card["label"]: card["value"] for card in client.get("/api/calibration/stats").json()["cards"]}
    for label, status in (("待校准记录", "待校准"), ("合格记录", "已合格"), ("不合格记录", "不合格")):
        total = client.get("/api/calibration", params={"status": status}).json()["total"]
        assert cards[label] == total


def test_gbk_encoded_file_is_accepted() -> None:
    p = prefix()
    summary = upload("gbk.csv", f"记录编号,仪器编号,校准机构\n{p}-1,INST-1,机构A\n".encode("gbk"))["summary"]
    assert summary["created"] == 1
