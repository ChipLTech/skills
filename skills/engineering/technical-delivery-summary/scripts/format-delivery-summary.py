#!/usr/bin/env python3
import json
import sys


VERBS = {
    "source_only": "source 中已实现",
    "build_only": "已完成 build",
    "historical_smoke": "历史 smoke 记录显示",
    "merged_not_released": "已合入",
    "released_not_validated": "已发布",
    "performance_workload": "已在声明 workload 下测得性能",
}


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in VERBS:
        return 2
    print(json.dumps({
        "summary": f"{VERBS[sys.argv[1]]} {sys.argv[2]}。",
        "claim_boundary": "Claim Boundary: 该表述只覆盖输入证据对应维度，未声明的 source、build、DLC Runtime、Real DLC Hardware、模型、性能或 release 状态保持未验证。",
        "qualification_artifact_created": False,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
