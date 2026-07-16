from app.providers.odds_api import OddsApiProvider
from app.providers.football_data import FootballDataProvider
from app.providers.api_futebol import ApiFutebolProvider
from app.providers.api_sports import ApiSportsProvider
ODDS_PROVIDERS={"odds_api":OddsApiProvider()}
SPORTS_PROVIDERS={"football_data":FootballDataProvider(),"api_futebol":ApiFutebolProvider(),"api_sports":ApiSportsProvider()}
# SofaScore, WhoScored, FootyStats, FotMob, Flashscore, Transfermarkt e sites de casas
# devem ser conectados somente por API/licença autorizada. O domínio não depende do fornecedor.
