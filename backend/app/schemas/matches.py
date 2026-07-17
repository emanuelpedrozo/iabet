from datetime import datetime
from pydantic import BaseModel, ConfigDict
class TeamOut(BaseModel):
    model_config=ConfigDict(from_attributes=True); id:int; name:str; short_name:str; crest_url:str|None=None; elo:float; attack_strength:float; defense_strength:float
class MatchListOut(BaseModel):
    id:int; kickoff:datetime; venue:str|None; status:str; competition:str; home_team:TeamOut; away_team:TeamOut; favorite:str|None=None; best_value:dict|None=None; model_pick:dict|None=None; probabilities:dict|None=None
class AnalysisOut(BaseModel):
    match: MatchListOut; prediction:dict; odds:list[dict]; value_bets:list[dict]; comparison:dict; h2h:list[dict]; players:dict; historical_stats:dict; generated_at:datetime
