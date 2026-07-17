import { BookOpen, Calculator, CircleHelp, Goal, Shield, UserRound } from 'lucide-react';

type Term = { term: string; name: string; description: string; example?: string };

const groups: { id: string; title: string; description: string; icon: React.ReactNode; terms: Term[] }[] = [
  {
    id: 'apostas', title: 'Odds e apostas', description: 'Como o IABet compara preço, risco e retorno.', icon: <Calculator />,
    terms: [
      { term: 'Odd', name: 'Cotação', description: 'Multiplicador do retorno bruto. Também representa o preço oferecido pela casa.', example: 'Odd 2,00 retorna R$ 20 em uma aposta de R$ 10, incluindo o valor apostado.' },
      { term: 'Odd justa', name: 'Preço justo do modelo', description: 'Odd calculada pela probabilidade estimada, sem margem da casa: 1 ÷ probabilidade.', example: 'Probabilidade de 50% corresponde a uma odd justa de 2,00.' },
      { term: 'Prob. implícita', name: 'Probabilidade da odd', description: 'Probabilidade sugerida pela cotação: 1 ÷ odd. Pode conter a margem da casa.' },
      { term: 'Value bet', name: 'Aposta de valor', description: 'Ocorre quando a odd disponível paga mais do que o preço justo estimado pelo modelo. Não significa que a aposta vai ganhar.' },
      { term: 'Edge', name: 'Vantagem estimada', description: 'Diferença entre a probabilidade do modelo e a probabilidade implícita da odd.', example: 'Modelo 55% e odd implícita 50% resultam em edge de 5 pontos percentuais.' },
      { term: 'EV', name: 'Valor esperado', description: 'Retorno médio teórico no longo prazo. É calculado por probabilidade × odd − 1.' },
      { term: 'Stake', name: 'Tamanho da entrada', description: 'Parcela da banca sugerida para a aposta. No IABet, “u” significa unidade.' },
      { term: 'Kelly', name: 'Critério de Kelly', description: 'Método para dimensionar a stake usando probabilidade e odd. O sistema usa uma fração conservadora.' },
      { term: 'De-vig', name: 'Remoção da margem', description: 'Ajuste que retira matematicamente a margem embutida nas odds da casa.' },
    ],
  },
  {
    id: 'modelo', title: 'Modelo e confiança', description: 'Leitura das projeções exibidas na análise.', icon: <BookOpen />,
    terms: [
      { term: '1X2', name: 'Resultado da partida', description: '1 representa mandante, X representa empate e 2 representa visitante.' },
      { term: 'Palpite do modelo', name: 'Resultado mais provável', description: 'Resultado com a maior probabilidade estimada. Pode ser o mais provável e, ainda assim, não oferecer value na odd atual.' },
      { term: 'Recomendação', name: 'Value conservador', description: 'Value que também atende aos limites de probabilidade, confiança, odd e coerência com o cenário principal.' },
      { term: 'Especulativa', name: 'Value de maior risco', description: 'Pode ter valor matemático, mas possui probabilidade ou confiança insuficiente para ser a indicação principal.' },
      { term: 'Confiança', name: 'Qualidade da estimativa', description: 'Combina concordância entre modelos, tamanho da amostra, edge, movimento e cobertura das odds.' },
      { term: 'Placar provável', name: 'Moda do placar', description: 'Placar individual com maior probabilidade. Não precisa coincidir isoladamente com a soma das probabilidades de vitória, empate ou derrota.' },
    ],
  },
  {
    id: 'partida', title: 'Estatísticas da partida', description: 'Médias por jogo da amostra recente selecionada.', icon: <Goal />,
    terms: [
      { term: 'J', name: 'Por jogo', description: 'Quando aparece após uma métrica, indica a média por partida da amostra.' },
      { term: 'xG', name: 'Gols esperados', description: 'Qualidade total das chances criadas. Um xG de 1,50 representa chances que, em média, gerariam 1,5 gol.' },
      { term: 'Chutes/J', name: 'Finalizações por jogo', description: 'Média de todas as tentativas de finalização.' },
      { term: 'No alvo/J', name: 'Finalizações certas', description: 'Média de chutes direcionados ao gol, normalmente exigindo defesa ou resultando em gol.' },
      { term: 'Escanteios/J', name: 'Escanteios por jogo', description: 'Média de tiros de canto conquistados pelo time.' },
      { term: 'Faltas/J', name: 'Faltas por jogo', description: 'Média de infrações cometidas pelo time.' },
      { term: 'Amarelos/J', name: 'Cartões amarelos', description: 'Média de amarelos recebidos por partida.' },
      { term: 'BTTS', name: 'Ambas marcam', description: 'Mercado em que os dois times precisam marcar ao menos um gol.' },
      { term: 'Over / Under', name: 'Mais de / Menos de', description: 'Indica se o total ficará acima ou abaixo de uma linha, como mais de 2,5 gols.' },
    ],
  },
  {
    id: 'jogadores', title: 'Scouts de jogadores', description: 'Médias e frequência de acerto dos atletas nos jogos recentes.', icon: <UserRound />,
    terms: [
      { term: 'ATA / MEI / LAT / ZAG / GOL', name: 'Posições', description: 'Atacante, meio-campista, lateral, zagueiro e goleiro.' },
      { term: 'Desarmes/J', name: 'Desarmes por jogo', description: 'Média de ações em que o atleta recupera a bola do adversário.' },
      { term: 'Faltas comet./J', name: 'Faltas cometidas', description: 'Média de infrações praticadas pelo jogador.' },
      { term: 'Faltas sofr./J', name: 'Faltas sofridas', description: 'Média de vezes em que o jogador recebe uma falta.' },
      { term: 'Gols/J e assistências/J', name: 'Participações por jogo', description: 'Média de gols ou assistências dividida pelo número de partidas da amostra.' },
      { term: 'Defesas/J', name: 'Defesas do goleiro', description: 'Média de finalizações defendidas pelo goleiro por partida.' },
      { term: 'Clean sheet', name: 'Jogo sem sofrer gol', description: 'Partida em que o goleiro ou a equipe termina sem sofrer gols.' },
      { term: '1+ / 2+ / 3+', name: 'Frequência de ocorrência', description: 'Percentual de jogos em que o atleta atingiu ao menos aquela quantidade.', example: '1+ chute 70% significa que chutou pelo menos uma vez em 70% dos jogos da amostra.' },
      { term: 'Nome verde', name: 'Tendência forte', description: 'O atleta atingiu alguma linha em pelo menos 70% de uma amostra mínima de cinco jogos. Não considera a odd sozinho.' },
    ],
  },
  {
    id: 'risco', title: 'Risco e uso responsável', description: 'Limites importantes para interpretar os números.', icon: <Shield />,
    terms: [
      { term: 'Amostra', name: 'Jogos considerados', description: 'Quantidade de partidas usada no cálculo. Os filtros geral, mandante e visitante formam amostras diferentes.' },
      { term: 'Últimos 10', name: 'Recorte recente', description: 'As médias usam no máximo as dez partidas finalizadas mais recentes disponíveis na condição escolhida.' },
      { term: '70% não é certeza', name: 'Frequência histórica', description: 'Indica o que ocorreu na amostra, não uma garantia para a próxima partida. Escalação, minutos, adversário e odd precisam ser avaliados.' },
    ],
  },
];

export default function Ajuda() {
  return <main className="mx-auto max-w-6xl px-5 pb-16 pt-8">
    <header className="card overflow-hidden p-6 md:p-9">
      <div className="flex max-w-3xl items-start gap-4"><span className="rounded-2xl bg-brand/10 p-3 text-brand"><CircleHelp size={26}/></span><div><div className="label text-brand">Central de ajuda</div><h1 className="mt-2 text-3xl font-black md:text-4xl">Glossário do IABet</h1><p className="mt-3 leading-7 text-muted">Consulte o significado das siglas, métricas e indicadores usados nas análises. Os números são apoio para decisão, não garantia de resultado.</p></div></div>
    </header>
    <nav className="mt-5 flex flex-wrap gap-2" aria-label="Categorias do glossário">{groups.map(g=><a key={g.id} href={`#${g.id}`} className="rounded-full border border-line bg-panel px-4 py-2 text-sm text-muted transition hover:border-brand/40 hover:text-white">{g.title}</a>)}</nav>
    <div className="mt-5 space-y-5">{groups.map(group=><section id={group.id} key={group.id} className="card scroll-mt-24 p-5 md:p-6"><div className="flex items-center gap-3"><span className="text-brand [&>svg]:h-5 [&>svg]:w-5">{group.icon}</span><div><h2 className="text-xl font-bold">{group.title}</h2><p className="mt-1 text-sm text-muted">{group.description}</p></div></div><div className="mt-5 grid gap-3 md:grid-cols-2">{group.terms.map(item=><article key={item.term} className="rounded-xl border border-line bg-white/[.018] p-4"><div className="flex flex-wrap items-baseline gap-x-2"><b className="text-brand">{item.term}</b><span className="text-sm text-white">{item.name}</span></div><p className="mt-2 text-sm leading-6 text-muted">{item.description}</p>{item.example&&<p className="mt-2 rounded-lg bg-brand/[.05] px-3 py-2 text-xs leading-5 text-brand/80"><b>Exemplo:</b> {item.example}</p>}</article>)}</div></section>)}</div>
  </main>;
}
