"""도구 층: 공연장 정보는 DB 에서 읽고, 위치는 등록된 공식 공연장 주소로만 Nominatim 에 묻는지 확인한다(conftest 의 가짜 Nominatim, 네트워크 없이)."""
import requests

from app.core.config import NOMINATIM_USER_AGENT
from app.tools import venue
from app.tools.fan_db import fetch_all
from app.tools.venue import geocode_address, get_venue_for_event


def test_venue_geocodes_registered_address(fake_nominatim):
    """공연 id 로 찾은 공연장의 DB 주소만 지오코딩하고, 앱 이름(User-Agent)을 밝힌다."""
    for event_id in ["E01", "E02", "E03"]:
        result = get_venue_for_event(event_id)
        assert result["lat"] == 37.5227
        assert result["lon"] == 127.1187
        assert result["note"] != ""
    addresses = []
    for request in fake_nominatim.requests:
        addresses.append(request["params"]["q"])
    assert addresses == ["서울특별시 송파구 올림픽로 424", "부산광역시 해운대구 APEC로 55", "대구광역시 북구 엑스코로 10"]
    assert fake_nominatim.requests[0]["headers"]["User-Agent"] == NOMINATIM_USER_AGENT
    assert get_venue_for_event("E02")["name"] == "루미너스홀 부산"
    # 서울 공연장 안내에는 공지(tkt-01)의 주차 안내가 들어 있다(공연장 경로는 검색 없이 이 글로 답한다)
    assert "주차" in get_venue_for_event("E01")["note"]


def test_location_not_stored_in_db():
    """venues 표에는 좌표 열이 없다(찾은 위치를 DB 에 저장하지 않는다)."""
    columns = []
    for row in fetch_all("PRAGMA table_info(venues)"):
        columns.append(row["name"])
    assert "lat" not in columns
    assert "lon" not in columns


def test_no_location_when_nominatim_fails(fake_nominatim):
    """네트워크 오류나 빈 결과면 위도, 경도만 None 이고 나머지 정보는 그대로다."""
    fake_nominatim.error = requests.ConnectionError("지도 서비스 꺼짐")
    result = get_venue_for_event("E01")
    assert result["lat"] is None
    assert result["name"] == "루미너스홀"

    fake_nominatim.error = None
    fake_nominatim.results = []
    assert get_venue_for_event("E01")["lon"] is None


def test_waits_between_requests(monkeypatch):
    """요청 사이가 1초보다 짧으면 남은 시간만큼 기다린다(Nominatim 이용 규칙: 초당 한 번)."""
    waits = []
    monkeypatch.setattr(venue, "NOMINATIM_INTERVAL_SECONDS", 1.0)
    monkeypatch.setattr(venue, "last_request_time", 0.0)
    monkeypatch.setattr(venue.time, "sleep", waits.append)
    geocode_address("서울특별시 송파구 올림픽로 424")
    geocode_address("부산광역시 해운대구 APEC로 55")
    assert len(waits) == 1
    assert 0.5 < waits[0] <= 1.0


def test_unknown_event(fake_nominatim):
    """없는 공연 id 는 None 이고 Nominatim 을 부르지 않는다."""
    assert get_venue_for_event("E99") is None
    assert fake_nominatim.requests == []
