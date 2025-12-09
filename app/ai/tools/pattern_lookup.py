# === 라이브러리 ===
import json
from pathlib import Path
from typing import Dict, Any, List, Optional


# === 공통 변수 정의 ===
# tools/cluster_pattern_data.json (BRENT/EIA/COT -> cluster_x 구조)
PATTERN_DATA_PATH: Path = Path(__file__).resolve().parent / "cluster_pattern_data.json"


# === 공통 함수 정의 ===
def _load_pattern_data() -> Dict[str, Any]:
    """클러스터별 BRENT/EIA/COT 패턴 JSON 로드."""
    with PATTERN_DATA_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data


# === 실행 함수 정의 ===
def run_pattern_lookup(
    cluster_id: str,
    sections: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    뉴스 클러스터 ID에 대응하는 과거 정형 데이터 패턴을 조회한다.

    - cluster_id 예: "cluster_8"
    - sections: ["BRENT", "EIA", "COT"] 중 선택, None이면 세 개 모두 조회
    - 반환: 해당 클러스터에 대해 섹션별 x/y/n_events/target/freq/horizon 정보
    """
    data = _load_pattern_data()

    if sections is None:
        sections = ["BRENT", "EIA", "COT"]

    out: Dict[str, Any] = {}
    for sec in sections:
        sec_dict = data.get(sec, {})
        if cluster_id in sec_dict:
            out[sec] = sec_dict[cluster_id]

    return {
        "cluster_id": cluster_id,
        "sections": out,
    }
