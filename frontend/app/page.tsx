import {getMatches,getStandings,type Match,type Standings} from '@/lib/api';
import {HomeDashboard} from '@/components/home-dashboard';

export default async function Home(){
  let matches:Match[]=[];
  let error='';
  let standings:Standings|null=null;
  const [matchesResult,standingsResult]=await Promise.allSettled([getMatches(),getStandings()]);
  if(matchesResult.status==='fulfilled')matches=matchesResult.value;else error='Não foi possível acessar a API. Inicie os serviços pelo Docker Compose.';
  if(standingsResult.status==='fulfilled')standings=standingsResult.value;
  return <HomeDashboard matches={matches} standings={standings} error={error}/>;
}
