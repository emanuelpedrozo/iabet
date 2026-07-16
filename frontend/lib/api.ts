export const API=process.env.NEXT_PUBLIC_API_URL||'http://localhost:8000/api/v1';
const SERVER_API=process.env.API_INTERNAL_URL||API;
export type Team={id:number;name:string;short_name:string;elo:number;attack_strength:number;defense_strength:number};
export type Match={id:number;kickoff:string;venue?:string;status:string;competition:string;home_team:Team;away_team:Team;favorite:string;probabilities:{home:number;draw:number;away:number};best_value?:{market:string;selection:string;odd:number;edge:number;strength:string}};
export async function getMatches():Promise<Match[]>{const r=await fetch(`${SERVER_API}/matches`,{cache:'no-store'});if(!r.ok)throw new Error('API indisponível');return r.json()}
export async function getAnalysis(id:string){const r=await fetch(`${SERVER_API}/matches/${id}`,{cache:'no-store'});if(!r.ok)throw new Error('Análise indisponível');return r.json()}
