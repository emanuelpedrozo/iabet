from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from pathlib import Path

OUT = Path('relatorios_apostas')
OUT.mkdir(exist_ok=True)
PDF = OUT / 'analise_brasileirao_16-17-07-2026.pdf'

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='TitleX', parent=styles['Title'], textColor=colors.HexColor('#0b3d2e'), fontSize=22, leading=26, alignment=TA_CENTER))
styles.add(ParagraphStyle(name='H1X', parent=styles['Heading1'], textColor=colors.HexColor('#0b3d2e'), fontSize=15, leading=18, spaceBefore=10, spaceAfter=6))
styles.add(ParagraphStyle(name='H2X', parent=styles['Heading2'], textColor=colors.HexColor('#176b4d'), fontSize=12, leading=15, spaceBefore=8, spaceAfter=4))
styles.add(ParagraphStyle(name='BodyX', parent=styles['BodyText'], fontSize=8.6, leading=12, spaceAfter=5))
styles.add(ParagraphStyle(name='SmallX', parent=styles['BodyText'], fontSize=7.2, leading=9.2, textColor=colors.HexColor('#333333')))
styles.add(ParagraphStyle(name='Callout', parent=styles['BodyText'], fontSize=9, leading=12, backColor=colors.HexColor('#eaf4ef'), borderColor=colors.HexColor('#176b4d'), borderWidth=.5, borderPadding=7, spaceBefore=5, spaceAfter=7))

def P(x, style='BodyX'): return Paragraph(x, styles[style])
def table(rows, widths, header=True, fs=7.2):
    t=Table([[P(str(c),'SmallX') for c in r] for r in rows], colWidths=widths, repeatRows=1 if header else 0, hAlign='LEFT')
    cmd=[('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.3,colors.HexColor('#aab7b1')),('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]
    if header: cmd += [('BACKGROUND',(0,0),(-1,0),colors.HexColor('#0b3d2e')),('TEXTCOLOR',(0,0),(-1,0),colors.white)]
    for i in range(1 if header else 0,len(rows)):
        if i%2==0: cmd.append(('BACKGROUND',(0,i),(-1,i),colors.HexColor('#f2f6f4')))
    t.setStyle(TableStyle(cmd)); return t

def footer(canvas, doc):
    canvas.saveState(); canvas.setFont('Helvetica',7); canvas.setFillColor(colors.grey)
    canvas.drawString(15*mm,9*mm,'Relatório analítico — captura de mercado: 16/07/2026, aproximadamente 09h–12h BRT')
    canvas.drawRightString(195*mm,9*mm,f'Página {doc.page}'); canvas.restoreState()

story=[]
story += [Spacer(1,22*mm),P('BRASILEIRÃO 2026','TitleX'),P('Análise pré-jogo e apostas de valor<br/>16 e 17 de julho de 2026','TitleX'),Spacer(1,8*mm),P('<b>Jogos:</b> Botafogo x Santos; Vitória x Vasco; Bahia x Chapecoense; Fluminense x Red Bull Bragantino; Mirassol x Grêmio.','Callout'),P('<b>Resumo executivo.</b> O melhor preço simples identificado é Fluminense para vencer a 1,95–1,99, seguido de Bahia -0,75 se a linha estiver em 1,70 ou melhor. Botafogo x Santos tem ausências ofensivas relevantes e favorece linhas conservadoras de gols. Vitória x Vasco e Mirassol x Grêmio têm maior incerteza após a pausa da Copa e devem receber stake menor. Não há aposta garantida; apostas não são investimento. Somente maiores de 18 anos.','BodyX'),P('Documento preparado em 16/07/2026. Odds são voláteis; reconferir preço, escalação e árbitro 30–60 minutos antes.','SmallX'),PageBreak()]

story += [P('Metodologia, leitura das probabilidades e limites','H1X'),P('A estimativa combina força no campeonato, mando, gols marcados/sofridos, forma pré-pausa, notícias de elenco, descanso e histórico recente. Para os mercados de chutes, a janela pedida é de 10 partidas; porém os feeds públicos consultáveis nesta captura não exibiram uma série completa e auditável de 10 jogos para todos os atletas. Por isso, o relatório apresenta somente <b>gatilhos condicionais</b> de chutes — não os rotula como value bet sem escalação e preço verificável. H2H recebe peso baixo, pois elencos e treinadores mudam.','BodyX'),P('<b>Probabilidade implícita</b> = 1/odd (sem remoção da margem). <b>Edge</b> = probabilidade estimada − implícita. <b>EV por unidade</b> = p × odd − 1. Uma aposta só entra se a odd disponível for igual ou maior à odd mínima indicada. Confiança mede qualidade/suficiência do dado, não certeza do resultado.','BodyX')]
rows=[['Mercado / jogo','Odd ref.','P est.','P impl.','Edge','EV','Conf.','Decisão'],
['Fluminense vence x Bragantino','1,95','54,0%','51,3%','+2,7 pp','+5,3%','★★★★☆','Value leve ≥1,91'],
['Bahia -0,75 x Chapecoense','1,72*','64,0%','58,1%','+5,9 pp','+10,1%','★★★★☆','Value ≥1,66'],
['Botafogo vence x Santos','2,08','50,0%','48,1%','+1,9 pp','+4,0%','★★★☆☆','Stake baixa ≥2,00'],
['Vitória DNB x Vasco','1,62*','65,0%','61,7%','+3,3 pp','+5,3%','★★★☆☆','Value ≥1,56'],
['Mirassol DNB x Grêmio','1,45*','72,0%','69,0%','+3,0 pp','+4,4%','★★★☆☆','Value ≥1,39'],
['Botafogo–Santos: menos 3,5 gols','1,40*','76,0%','71,4%','+4,6 pp','+6,4%','★★★☆☆','Peça de múltipla ≥1,35'],
['Fluminense–Bragantino: +1,5 gols','1,30*','80,0%','76,9%','+3,1 pp','+4,0%','★★★☆☆','Peça de múltipla ≥1,25']]
story += [P('Carteira de value bets','H1X'),table(rows,[45*mm,15*mm,15*mm,16*mm,14*mm,13*mm,18*mm,35*mm]),P('* Linha indicativa observada em comparadores/mercado agregado, não atribuível com segurança a uma casa específica na página pública. Exigir o preço mínimo antes de apostar. As cotações 1X2 verificadas diretamente estão detalhadas em cada jogo.','SmallX'),P('<b>Gestão sugerida:</b> 0,50 unidade no Fluminense; 0,40 no Bahia -0,75; 0,25 nas demais simples. Não somar exposição excessiva repetindo a mesma seleção em simples, dupla e tripla.','Callout'),PageBreak()]

games=[
('Botafogo x Santos — 16/07, 19h30, Nilton Santos',
'Botafogo é favorito curto: mercado 1X2 observado 2,05–2,12 / 3,43–3,50 / 3,50–3,80. Ambos chegam próximos na tabela: Botafogo 12º, 22 pontos; Santos 21 pontos em 18 jogos. O mando equilibra uma equipe alvinegra que oscilou antes da pausa (D/E/V nas três últimas rodadas).',
'<b>Botafogo provável:</b> Léo Linck; Vitinho (Mateo Ponte), Ferraresi, Justino, Alex Telles; Huguinho, Medina, Lucas Villalba, Matheus Martins; Lucas Emanuel, Kauan Toledo.<br/><b>Fora:</b> Danilo (pós-Copa), Júnior Santos, Allan, Kaio Pantaleão e Arthur Cabral (dores).<br/><b>Santos provável:</b> Gabriel Brazão; Gabriel Menino, Lucas Veríssimo, Luan Peres, Escobar; Willian Arão, Gustavo Henrique, Rollheiser; Miguelito, Rony, Barreal.<br/><b>Fora:</b> Neymar, Gabigol (suspenso), João Schmidt e Moisés.',
'Sem Arthur Cabral, Neymar e Gabigol, cai a qualidade das finalizações e a concentração de chutes muda. Preferência: menos de 3,5 gols; vitória seca do Botafogo apenas ≥2,00. Para chutes, aguardar titulares: Matheus Martins 2+ finalizações somente ≥1,65; Barreal 2+ somente ≥1,80. Cartões: vários pendurados no Santos e jogo de seis pontos, mas sem linha/árbitro histórico auditável não há value formal. Escanteios: apenas under 12,5 como complemento se ≥1,30.'),
('Vitória x Vasco — 16/07, 19h30, Barradão',
'Vitória 13º com 22 pontos; Vasco abre a rodada no Z4 com 20. Mercado: Vitória 2,26–2,38 (11/8 melhor preço), empate ~3,30, Vasco ~3,20. O mando e a situação de tabela favorecem o Vitória, mas a estreia do técnico Pedro Emanuel no Vasco aumenta a variância.',
'<b>Leitura de elenco:</b> confirmar as escalações oficiais; o mercado lista Renzo López/Renato Kayzer/Marinho entre referências ofensivas e Andrés Gómez/Matheus França/Brenner do lado vascaíno. Por não haver provável XI completa confirmada em fonte aberta capturada, não se deve apostar em props antes dos titulares.',
'Aposta preferida: Vitória empate anula (DNB) ≥1,56, estimativa 65%. Alternativa agressiva: Vitória vence ≥2,30, p=44% (implícita 43,5%; edge pequeno). O placar modal é 1–0/1–1. Chutes: somente após escalação; atacante central titular 2+ chutes ≥1,55. Cartões têm apelo pela pressão de tabela, mas exigir over 4,5 ≥1,80 e confirmação de árbitro; caso contrário, passar.'),
('Bahia x Chapecoense — 17/07, 19h30, Fonte Nova',
'Jogo atrasado da 4ª rodada. Bahia é o favorito mais forte do lote: melhores preços públicos próximos de 1,48 para casa, 5,00 empate e 7,00 visitante. A linha reflete forte diferença de elenco e mando. A pausa, contudo, reduz confiança em ritmo competitivo.',
'<b>Bahia:</b> Willian José, Everton Ribeiro/Jean Lucas, Luciano Juba e Erick Pulga são referências; Alejo Véliz, Marco Moreno e Guido Herrera ainda não podem estrear porque a janela internacional abre dia 20. Confirmar o XI. <b>Chapecoense:</b> tendência de bloco mais baixo; confirmar Marcinho e demais atacantes na súmula.',
'Vitória simples a 1,48 tem preço justo aproximado 1,45 e pouco edge. Melhor estrutura: Bahia -0,75 ≥1,66 (p equivalente estimada 64%); protege meia perda em vitória mínima, conforme regra asiática. Mais de 1,5 gols do Bahia somente ≥1,65. Chutes: Willian José 2+ ≥1,55 ou 1+ no alvo ≥1,75 se titular. Escanteios Bahia over 5,5 só ≥1,75.'),
('Fluminense x RB Bragantino — 17/07, 20h, Maracanã',
'Duelo de topo: Fluminense 3º (31 pontos, 9V/4E/5D, saldo +5); Bragantino 5º (29, 9V/2E/7D, saldo +6). Odds verificadas: Flu 1,91–1,99; empate 3,30–3,50; Braga 4,00–4,33. Flu venceu quatro seguidas em casa e está invicto há seis como mandante; o Bragantino vinha cinco jogos invicto, três vitórias seguidas.',
'<b>Flu provável:</b> Fábio; Guga, Jemmes, Freytes, Renê (Arana); Hércules, Martinelli; Kevin Serna, Lucho Acosta, Savarino; John Kennedy (Hulk). Cano e Matheus Reis fora; Samuel Xavier suspenso; Hulk pode estrear.<br/><b>Braga provável:</b> Volpi; Sant’Anna, Alix, Gustavo Marques, Cauê; Matheus Fernandes (Rodriguinho), Eric Ramires, Lucas Barbosa; Fernando, Herrera, Eduardo Sasha. Juninho Capixaba suspenso; desfalques incluem Fabrício, Fabinho e Vanderlan.',
'Value principal: Fluminense vence ≥1,91 (p 54%). +1,5 gols ≥1,25 serve para múltipla; over 2,5 a ~1,85–2,05 não tem edge claro. H2H recente: Flu 3V, 1E, 2D nos seis listados; BTTS em 4/6 e over 2,5 em 4/6, mas peso baixo. Chutes: John Kennedy 3+ ≥1,85 se for centroavante; Hulk 2+ ≥1,60 apenas se titular e sem restrição de minutos.'),
('Mirassol x Grêmio — 17/07, 20h, José Maria de Campos Maia',
'Confronto da parte baixa: Mirassol 19º com 16 pontos; Grêmio 21, na borda do Z4. Mercado 1X2 público: Mirassol 2,00; empate 3,40; Grêmio 4,00. O favoritismo do mandante é coerente, mas o preço seco exige cerca de 50% e não oferece folga suficiente.',
'Confirmar os titulares após a longa pausa. O Grêmio tem compromisso de playoff da Sul-Americana na semana seguinte, possível fator de gestão física. O Mirassol teve campanha histórica em 2025, mas os resultados de 2026 mostram regressão forte; não extrapolar o desempenho do ano anterior.',
'Preferência: Mirassol DNB ≥1,39 (p 72% de não perder no enquadramento do modelo; push no empate). Vitória seca só ≥2,08. Menos de 3,5 gols pode compor múltipla ≥1,35. Props de chutes/cartões ficam sem entrada até XI e linhas. H2H tem baixa amostra e pouca utilidade preditiva neste contexto.')]

for title,ctx,lineup,bet in games:
    story += [P(title,'H1X'),P('<b>Cenário e favoritismo.</b> '+ctx),P('<b>Escalações, ausências e jogadores-chave.</b> '+lineup),P('<b>Mercados.</b> '+bet),Spacer(1,2*mm)]

story += [PageBreak(),P('Dupla e tripla-alvo (odd total entre 3 e 4)','H1X'),P('<b>Dupla principal — odd aproximada 3,35:</b> Fluminense vence (1,95) × Bahia -0,75 (1,72). Probabilidade conjunta independente aproximada 34,6%; implícita 29,9%; EV teórico ~+15,8%. Faz sentido porque reúne os dois mandantes com maior superioridade mensurável. Correlação praticamente nula por serem jogos distintos. Stake máxima: 0,25 unidade.','Callout'),P('<b>Tripla conservadora — odd aproximada 3,55:</b> Fluminense vence (1,95) × Botafogo–Santos menos de 3,5 gols (1,40) × Fluminense–Bragantino mais de 1,5 gols (1,30). Probabilidade conjunta bruta ~32,8%; implícita 28,2%; EV ~+16%. Atenção: duas pernas pertencem ao jogo do Fluminense e, portanto, não são independentes; o cálculo bruto superestima um pouco o EV. Só usar se a casa permitir e a odd combinada permanecer ≥3,30. Stake 0,15 unidade.','Callout'),P('<b>Alternativa sem correlação interna — odd aproximada 3,26:</b> Bahia -0,75 (1,72) × Vitória DNB (1,62) × Botafogo–Santos menos de 3,5 (1,17–1,20 numa linha mais conservadora de under 4,5). Use apenas se cada preço individual superar seu mínimo.','BodyX'),P('Não perseguir odd 3–4 acrescentando escanteios ou cartões sem edge. A construção correta parte de pernas individualmente aceitáveis; múltiplas ampliam a variância e a margem efetiva da casa.','BodyX'),P('Checklist pré-jogo','H1X'),P('1. Confirmar titulares, sobretudo Arthur Cabral, Hulk/John Kennedy, Willian José e centroavantes de Vitória/Vasco. 2. Conferir odds na Bet365, Pinnacle, Betano, Superbet e Sportingbet; apostar somente acima da odd mínima. 3. Retirar prop de jogador se ele não iniciar ou houver limite de minutos. 4. Verificar movimento superior a 8%: investigar notícia antes de entrar. 5. Não elevar stake para compensar perda anterior.','BodyX')]

sources=[
['Fonte','Uso no relatório'],
['CBF — agenda oficial: cbf.com.br/futebol-brasileiro/jogos/campeonato-brasileiro/serie-a/2026/','Datas, competição e mando'],
['ge — ge.globo.com/ba/futebol/brasileirao-serie-a/noticia/2026/07/16/','Prováveis escalações e ausências de Botafogo–Santos; agenda da rodada'],
['UOL — uol.com.br/esporte/futebol/ultimas-noticias/2026/07/16/abre-retorno-brasileirao.ghtm','Tabela contextual, pausa, desfalques e agenda'],
['SportyTrader — sportytrader.com/pt-br/odds/botafogo-rj-santos-7982933/','Odds 1X2 Botafogo–Santos'],
['SportyTrader — sportytrader.com/pt-br/odds/fluminense-rj-bragantino-sp-7982932/','Odds e totais Flu–Braga'],
['SportyTrader — sportytrader.com/pt-br/palpites/fluminense-rj-bragantino-sp-359254/','Forma, classificação, escalações, ausências e estatísticas Flu–Braga'],
['Oddschecker — oddschecker.com/football/world/brazil/serie-a/','Odds 1X2 e mercados listados dos cinco jogos'],
['Oddspedia — oddspedia.com/br/futebol/','Validação de horários e disponibilidade de mercados']]
story += [PageBreak(),P('Fontes, auditoria e ressalvas','H1X'),table(sources,[65*mm,115*mm]),Spacer(1,4*mm),P('Captura realizada em 16/07/2026. As páginas agregadoras podem mostrar casas diferentes conforme país, conta, limite e horário. “Odd média” neste relatório é uma referência central do conjunto publicamente visível; não equivale a uma oferta garantida. A Pinnacle e algumas casas brasileiras não tiveram todos os preços expostos nas páginas abertas consultadas. Nenhum dado foi atribuído a uma casa quando isso não pôde ser verificado.','BodyX'),P('<b>Limitação estatística:</b> não foi possível auditar uma base completa de chutes dos últimos 10 jogos para todos os prováveis titulares via páginas públicas. Os gatilhos de props são filtros operacionais, não recomendações finais. Cards/corners também recebem menor peso. Este material é informativo, não promessa de lucro.','Callout')]

doc=SimpleDocTemplate(str(PDF),pagesize=A4,rightMargin=14*mm,leftMargin=14*mm,topMargin=13*mm,bottomMargin=15*mm,title='Análise Brasileirão 16 e 17 de julho de 2026',author='Relatório analítico')
doc.build(story,onFirstPage=footer,onLaterPages=footer)
print(PDF.resolve())
