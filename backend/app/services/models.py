from dataclasses import dataclass
from math import exp, factorial
import numpy as np

@dataclass(frozen=True)
class ModelInput:
    home_attack: float; home_defense: float; away_attack: float; away_defense: float
    home_elo: float; away_elo: float; league_home_goals: float=1.42; league_away_goals: float=1.08

def poisson_pmf(k:int, lam:float)->float: return exp(-lam)*lam**k/factorial(k)
def expected_goals(x:ModelInput)->tuple[float,float]:
    return (max(.2,x.league_home_goals*x.home_attack*x.away_defense), max(.2,x.league_away_goals*x.away_attack*x.home_defense))
def poisson_matrix(h:float,a:float,max_goals:int=8)->np.ndarray:
    return np.outer([poisson_pmf(i,h) for i in range(max_goals+1)],[poisson_pmf(j,a) for j in range(max_goals+1)])
def poisson_model(x:ModelInput)->dict:
    h,a=expected_goals(x); m=poisson_matrix(h,a); home=float(np.tril(m,-1).sum()); draw=float(np.trace(m)); away=float(np.triu(m,1).sum())
    over25=float(sum(m[i,j] for i in range(9) for j in range(9) if i+j>2)); btts=float(sum(m[i,j] for i in range(1,9) for j in range(1,9)))
    score=np.unravel_index(np.argmax(m),m.shape)
    return {"home":home,"draw":draw,"away":away,"over_2_5":over25,"under_2_5":1-over25,"btts_yes":btts,"btts_no":1-btts,"xg_home":h,"xg_away":a,"score":f"{score[0]}-{score[1]}"}
def elo_model(x:ModelInput)->dict:
    expected=1/(1+10**(-((x.home_elo+70)-x.away_elo)/400)); draw=.25*exp(-abs(x.home_elo-x.away_elo)/500); return {"home":expected*(1-draw),"draw":draw,"away":1-expected*(1-draw)-draw}
def monte_carlo(x:ModelInput,n:int=30000,seed:int=42)->dict:
    h,a=expected_goals(x); rng=np.random.default_rng(seed); hs=rng.poisson(h,n); aw=rng.poisson(a,n)
    return {"home":float(np.mean(hs>aw)),"draw":float(np.mean(hs==aw)),"away":float(np.mean(hs<aw)),"over_2_5":float(np.mean(hs+aw>2)),"btts_yes":float(np.mean((hs>0)&(aw>0)))}
def ensemble(x:ModelInput)->dict:
    p,e,m=poisson_model(x),elo_model(x),monte_carlo(x); result={k:round(.45*p[k]+.25*e[k]+.30*m[k],4) for k in ("home","draw","away")}
    result.update({k:round(.65*p[k]+.35*m[k],4) for k in ("over_2_5","btts_yes")}); result["under_2_5"]=round(1-result["over_2_5"],4); result["btts_no"]=round(1-result["btts_yes"],4); result.update({"xg_home":round(p["xg_home"],2),"xg_away":round(p["xg_away"],2),"score":p["score"],"models":{"poisson":p,"elo":e,"monte_carlo":m},"version":"ensemble-1.0"}); return result

