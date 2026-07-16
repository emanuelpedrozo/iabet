import {getMatches,type Match} from '@/lib/api';
import {HomeDashboard} from '@/components/home-dashboard';

export default async function Home(){
  let matches:Match[]=[];
  let error='';
  try{matches=await getMatches()}catch{error='Não foi possível acessar a API. Inicie os serviços pelo Docker Compose.'}
  return <HomeDashboard matches={matches} error={error}/>;
}
