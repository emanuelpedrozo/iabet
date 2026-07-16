from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
@dataclass
class ProviderEvent: external_id:str; home:str; away:str; kickoff:datetime; payload:dict
class SportsDataProvider(ABC):
    name:str
    @abstractmethod
    async def fixtures(self,start:datetime,end:datetime)->list[ProviderEvent]: ...
    @abstractmethod
    async def statistics(self,external_id:str)->dict: ...
class OddsProvider(ABC):
    name:str
    @abstractmethod
    async def odds(self,external_ids:list[str])->list[dict]: ...

