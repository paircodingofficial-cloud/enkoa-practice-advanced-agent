"""도구 층: 공연의 공연장 이름, 주소, 찾아오는 길, 공연 시작 시각과 지도에 찍을 위치(위도, 경도)를 돌려준다.

이름, 주소, 찾아오는 길은 DB 의 venues 표에서 읽고, 위치는 요청마다 OpenStreetMap Nominatim 에 그 주소를 물어 찾는다.
찾은 위치는 DB 에 저장하지 않는다(화면에 지도를 그리는 데만 쓴다).
지오코딩하는 주소는 venues 표에 등록된 공식 공연장 주소뿐이다. 공연 id 로만 공연장을 찾으므로 팬이 보낸 임의 주소가 들어올 자리가 없다(사생 행위 방지, OOS-08).
Nominatim 이용 규칙대로 앱 이름(User-Agent)을 밝히고, 요청 사이를 1초 이상 띄운다.
위치를 못 찾으면(네트워크 오류, 결과 없음) 위도, 경도를 None 으로 두고 나머지 정보는 그대로 돌려준다. 화면은 이때 지도를 그리지 않는다.
db_path 를 주지 않으면 data/luna_fan.db 를 쓴다. 평가처럼 DB 사본으로 돌릴 때만 사본 경로를 넘긴다.
"""
import time

import requests

from app.core.config import DB_PATH, NOMINATIM_INTERVAL_SECONDS, NOMINATIM_URL, NOMINATIM_USER_AGENT
from app.tools.fan_db import fetch_all

# 마지막으로 Nominatim 에 요청한 시각(time.monotonic 값). 다음 요청 전에 남은 간격만큼 기다리는 데 쓴다
last_request_time = 0.0


# [보조 함수] Nominatim 요청 간격 지키기
def wait_for_nominatim() -> None:
    """앞 요청에서 NOMINATIM_INTERVAL_SECONDS 가 지나지 않았으면 남은 시간만큼 기다린다(돌려주는 값 없음)."""
    global last_request_time
    passed = time.monotonic() - last_request_time

    # 간격이 모자라면 모자란 만큼만 기다린다. 이미 지났으면 바로 넘어간다
    if passed < NOMINATIM_INTERVAL_SECONDS:
        time.sleep(NOMINATIM_INTERVAL_SECONDS - passed)

    # 이번 요청 시각을 남겨 다음 요청의 간격을 잰다
    last_request_time = time.monotonic()


# [외부 API] 주소를 위도, 경도로 바꾸기(OpenStreetMap Nominatim)
def geocode_address(address: str) -> dict | None:
    """주소 하나를 Nominatim 으로 찾아 {"lat": 위도, "lon": 경도} 를 돌려준다. 못 찾으면 None 이다."""
    # 이용 규칙: 요청 사이 1초, 앱 이름을 밝힌 User-Agent, 결과는 가장 맞는 한 곳만
    wait_for_nominatim()
    params = {"q": address, "format": "json", "limit": 1}
    headers = {"User-Agent": NOMINATIM_USER_AGENT}
    # 지도 서비스가 멈춰도 답변은 나가야 하므로 네트워크 오류는 '위치 없음'으로 본다
    try:
        response = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        results = response.json()
    except requests.RequestException:
        return None

    # 주소를 못 찾았으면 결과가 빈 목록이다
    if len(results) == 0:
        return None

    # 찾았으면 첫 결과의 위도, 경도(글자로 온다)를 숫자로 바꾼다
    return {"lat": float(results[0]["lat"]), "lon": float(results[0]["lon"])}


# [도구 함수] 공연장 이름, 주소, 위치
def get_venue_for_event(event_id: str, db_path=DB_PATH) -> dict | None:
    """공연 id 로 공연장 한 곳의 id, 이름, 주소, 찾아오는 길, 공연 이름, 시작 시각, 위도, 경도를 dict 로 돌려준다. 없는 공연이면 None 이다."""
    # 공연 표에는 공연장 id 만 있으므로 공연장 표를 이어 붙여 읽는다(fan_db 의 읽기 전용 연결)
    # "언제 어디서 해요?" 에도 답하도록 공연 시작 시각을 함께 읽는다
    query = """
        SELECT v.venue_id, v.name, v.address, v.note, e.title AS event_title, e.starts_at
        FROM events e JOIN venues v ON v.venue_id = e.venue_id
        WHERE e.event_id = ?
    """
    rows = fetch_all(query, (event_id,), db_path)

    # 없는 공연 id 면 None 이다
    if len(rows) == 0:
        return None
    venue = rows[0]

    # DB 에 등록된 공식 공연장 주소만 지오코딩한다. 찾은 위치는 DB 에 쓰지 않는다
    venue["lat"] = None
    venue["lon"] = None
    location = geocode_address(venue["address"])

    # 찾았을 때만 위치를 채운다. 못 찾으면 None 으로 두고 화면은 지도를 그리지 않는다
    if location is not None:
        venue["lat"] = location["lat"]
        venue["lon"] = location["lon"]
    return venue


if __name__ == "__main__":
    # 해당 모듈 테스트: uv run -m app.tools.venue (Nominatim 을 세 번 부른다, 무료)
    for check_event_id in ["E01", "E02", "E03"]:
        print(check_event_id, get_venue_for_event(check_event_id))
