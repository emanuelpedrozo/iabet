def kelly(probability:float, odd:float, fraction:float=.25)->float:
    b=odd-1; raw=(probability*odd-1)/b if b else 0; return max(0,raw)*fraction
def classify(edge:float)->str:
    return "muito forte" if edge>=.10 else "forte" if edge>=.06 else "moderada" if edge>=.03 else "fraca"
def evaluate(market:str,selection:str,odd:float,probability:float,bookmaker:str)->dict:
    implied=1/odd; edge=probability-implied; ev=probability*odd-1
    return {"market":market,"selection":selection,"bookmaker":bookmaker,"odd":odd,"estimated_probability":round(probability,4),"implied_probability":round(implied,4),"edge":round(edge,4),"expected_roi":round(ev,4),"is_value":ev>0,"kelly_fraction":round(kelly(probability,odd),4),"suggested_stake_units":round(min(kelly(probability,odd)*10,.75),2),"strength":classify(edge)}
def market_probability(pred:dict, market:str, selection:str)->float|None:
    mapping={("match_result","home"):"home",("match_result","draw"):"draw",("match_result","away"):"away",("goals_2_5","over"):"over_2_5",("goals_2_5","under"):"under_2_5",("btts","yes"):"btts_yes",("btts","no"):"btts_no"}
    key=mapping.get((market,selection)); return pred.get(key) if key else None

