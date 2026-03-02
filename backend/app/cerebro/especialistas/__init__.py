"""
Especialistas do Cérebro APEX — os 7 motores de análise por estratégia.

Cada especialista é independente e retorna a interface padrão: list[SugestaoMotor]
O CEO Brain (cerebro.gestor) recebe os candidatos de todos e decide o portfólio final.
"""

from dataclasses import dataclass, field


@dataclass
class SugestaoMotor:
    """Resultado padrão de qualquer especialista."""
    modulo: str          # etfs | fiis | momentum | wheel | alpha | dividendos | renda_fixa | caixa
    ticker: str          # código B3 (ex: PETR4, MXRF11, BOVA11)
    nome: str            # nome legível
    tipo: str            # ACAO | FII | ETF | BDR | RF | CAIXA
    quantidade: float    # inteiro para ações/FIIs/ETFs; valor nominal para RF/CAIXA
    preco_atual: float   # preço real de mercado
    valor_total: float   # quantidade × preco_atual
    justificativa: str   # explicação em linguagem natural do POR QUÊ
    score: float = 0.0   # score interno do especialista (maior = melhor)
    dados_extras: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "modulo":        self.modulo,
            "ticker":        self.ticker,
            "nome":          self.nome,
            "tipo":          self.tipo,
            "quantidade":    self.quantidade,
            "preco_atual":   round(self.preco_atual, 2),
            "valor_total":   round(self.valor_total, 2),
            "justificativa": self.justificativa,
            "score":         round(self.score, 3),
            "dados_extras":  self.dados_extras,
        }


__all__ = ["SugestaoMotor"]

