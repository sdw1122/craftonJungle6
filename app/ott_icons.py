# 실제 브랜드 로고 대신 서비스별 컬러 + 이니셜로 표시
OTT_ICONS = {
    "NETFLIX": {"text": "N", "color": "#E50914"},
    "TVING": {"text": "T", "color": "#FF0050"},
    "WAVVE": {"text": "W", "color": "#1E5FFF"},
    "DISNEY_PLUS": {"text": "D+", "color": "#113CCF"},
    "WATCHA": {"text": "왓", "color": "#FF0558"},
    "APPLE_TV_PLUS": {"text": "TV", "color": "#000000"},
}
DEFAULT_OTT_ICON = {"text": "?", "color": "#8899aa"}
BOX_OFFICE_ICON = {"text": "BOX", "color": "#e85d04"}

# TMDB watch-provider 이름(provider_name) -> 우리 ott_providers.code 매칭
# TMDB가 실제로 내려주는 표기와 다를 수 있어, 확인되는 대로 보정 필요
TMDB_PROVIDER_NAME_TO_CODE = {
    "Netflix": "NETFLIX",
    "wavve": "WAVVE",
    "TVING": "TVING",
    "Tving": "TVING",
    "Disney Plus": "DISNEY_PLUS",
    "Watcha": "WATCHA",
    "Apple TV Plus": "APPLE_TV_PLUS",
    "Apple TV": "APPLE_TV_PLUS",
}
