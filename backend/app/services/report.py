from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


def build_pdf(data: dict) -> bytes:
    buf = BytesIO()
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )
    m = data["match"]
    p = data["prediction"]
    story = [
        Paragraph("IABet — RELATORIO PROFISSIONAL", styles["Title"]),
        Paragraph(f'{m["home_team"].name} x {m["away_team"].name}', styles["Heading1"]),
        Paragraph(
            f'{m["competition"]} • {m["kickoff"]:%d/%m/%Y %H:%M} • {m["venue"] or "local a definir"}',
            styles["Normal"],
        ),
        Spacer(1, 8),
    ]
    story += [
        Paragraph("Resumo do modelo", styles["Heading2"]),
        Paragraph(
            f'Favorito: <b>{m["favorite"]}</b>. Placar modal {p["score"]}; '
            f'xG {p["xg_home"]:.2f}-{p["xg_away"]:.2f}. Ensemble 1.4: forma recente, '
            f"splits casa/fora, Dixon-Coles + ELO; escanteios/cartoes/chutes via TeamStat. "
            f"Value com de-vig, consenso e movimento de odds.",
            styles["BodyText"],
        ),
    ]
    rows = [["Mercado", "Selecao", "Casa", "Odd", "P est.", "P impl.", "Edge", "EV", "Kelly"]]
    for v in data["value_bets"][:10]:
        rows.append(
            [
                v["market"],
                v["selection"],
                v["bookmaker"],
                f'{v["odd"]:.2f}',
                f'{v["estimated_probability"]:.1%}',
                f'{v["implied_probability"]:.1%}',
                f'{v["edge"]:.1%}',
                f'{v["expected_roi"]:.1%}',
                f'{v["kelly_fraction"]:.1%}',
            ]
        )
    t = Table(rows, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b3d2e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story += [
        Paragraph("Value bets", styles["Heading2"]),
        t,
        Spacer(1, 8),
        Paragraph("Gestao de banca", styles["Heading2"]),
        Paragraph(
            "A stake e uma fracao conservadora de Kelly e possui teto. Odds mudam; "
            "valide precos e escalacoes antes da entrada. Apostas nao sao investimento "
            "e nao existe retorno garantido.",
            styles["BodyText"],
        ),
        Paragraph("Fontes e integridade", styles["Heading2"]),
        Paragraph(
            "Cada odd mantem casa e horario de captura. Conectores externos devem usar "
            "APIs e licencas autorizadas. Ausencia de dados reduz confianca; nunca e "
            "preenchida com informacao inventada.",
            styles["BodyText"],
        ),
    ]
    doc.build(story)
    return buf.getvalue()
