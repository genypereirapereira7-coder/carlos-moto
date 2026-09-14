"""Importa todos os módulos de modelo pra que `Base.metadata` veja toda tabela
e pra que as relações declaradas por nome de string (`Mapped["Moto"]`) achem
a classe correspondente no registro do SQLAlchemy."""

from app.models.base import Base, agora, como_utc
from app.models.cliente import Cliente
from app.models.despesa import DespesaMoto
from app.models.historico import AcaoHistorico, Historico
from app.models.moto import CondicaoMoto, Moto, StatusMoto
from app.models.parcela import Parcela, StatusParcela
from app.models.usuario import Papel, SessaoAuth, Usuario
from app.models.venda import FormaPagamento, Venda

__all__ = [
    "Base",
    "Cliente",
    "CondicaoMoto",
    "DespesaMoto",
    "AcaoHistorico",
    "Historico",
    "FormaPagamento",
    "Moto",
    "Papel",
    "Parcela",
    "SessaoAuth",
    "StatusMoto",
    "StatusParcela",
    "Usuario",
    "Venda",
    "agora",
    "como_utc",
]
