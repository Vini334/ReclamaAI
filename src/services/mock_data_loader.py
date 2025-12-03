"""
Carregador de dados mock para desenvolvimento.
Lê dados das 5 fontes de reclamações simuladas.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.config import get_settings
from src.models.schemas import ComplaintRaw, ComplaintSource, TeamInfo


class MockDataLoader:
    """Carrega dados mock dos arquivos JSON."""

    _instance: Optional["MockDataLoader"] = None
    _cache: Dict[str, Any] = {}

    def __new__(cls, data_path: Optional[str] = None) -> "MockDataLoader":
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, data_path: Optional[str] = None) -> None:
        """
        Inicializa o loader.

        Args:
            data_path: Caminho para pasta data/mock
        """
        if self._initialized:
            return

        settings = get_settings()
        self.data_path = Path(data_path or settings.mock_data_path)
        self._initialized = True

    def _load_json(self, filename: str) -> Dict[str, Any]:
        """
        Carrega arquivo JSON com cache.

        Args:
            filename: Nome do arquivo (sem caminho)

        Returns:
            Conteúdo do JSON
        """
        if filename in self._cache:
            return self._cache[filename]

        file_path = self.data_path / filename
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self._cache[filename] = data
        return data

    def _parse_datetime(self, dt_string: str) -> datetime:
        """Parse datetime string para objeto datetime."""
        try:
            return datetime.fromisoformat(dt_string.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return datetime.utcnow()

    def load_reclame_aqui(self) -> List[ComplaintRaw]:
        """
        Carrega reclamações do Reclame Aqui.

        Returns:
            Lista de ComplaintRaw normalizadas
        """
        data = self._load_json("reclame_aqui.json")
        complaints = []

        for item in data.get("complaints", []):
            complaint = ComplaintRaw(
                id=str(uuid.uuid4()),
                external_id=item["external_id"],
                source=ComplaintSource.RECLAME_AQUI,
                company_name=data.get("company", {}).get("name", "TechNova Store"),
                title=item["title"],
                description=item["description"],
                consumer_name=item["consumer_name"],
                created_at=self._parse_datetime(item["created_at"]),
                channel="Reclame Aqui",
                city=item.get("city"),
                state=item.get("state"),
                product_category=item.get("product_category"),
                status=item.get("status", "Não Processada"),
            )
            complaints.append(complaint)

        return complaints

    def load_jira_issues(self) -> List[ComplaintRaw]:
        """
        Carrega issues do Jira como reclamações.

        Returns:
            Lista de ComplaintRaw normalizadas
        """
        data = self._load_json("jira_issues.json")
        complaints = []

        for item in data.get("issues", []):
            complaint = ComplaintRaw(
                id=str(uuid.uuid4()),
                external_id=item["external_id"],
                source=ComplaintSource.JIRA,
                company_name="TechNova Store",
                title=item["title"],
                description=item["description"],
                consumer_name=item.get("reporter", "Não informado"),
                created_at=self._parse_datetime(item["created_at"]),
                channel="Jira",
                status=item.get("status", "Open"),
            )
            complaints.append(complaint)

        return complaints

    def load_chat_transcripts(self) -> List[ComplaintRaw]:
        """
        Carrega transcrições de chat/WhatsApp.

        Returns:
            Lista de ComplaintRaw normalizadas
        """
        data = self._load_json("chat_transcripts.json")
        complaints = []

        for item in data.get("transcripts", []):
            source = ComplaintSource.WHATSAPP if item.get("channel") == "WhatsApp" else ComplaintSource.CHAT
            complaint = ComplaintRaw(
                id=str(uuid.uuid4()),
                external_id=item["external_id"],
                source=source,
                company_name="TechNova Store",
                title=item["title"],
                description=item["transcript"],
                consumer_name=item["consumer_name"],
                consumer_contact=item.get("consumer_phone"),
                created_at=self._parse_datetime(item["created_at"]),
                channel=item.get("channel", "Chat"),
                city=item.get("city"),
                state=item.get("state"),
                status=item.get("status", "Aberta"),
            )
            complaints.append(complaint)

        return complaints

    def load_phone_transcripts(self) -> List[ComplaintRaw]:
        """
        Carrega transcrições de telefone.

        Returns:
            Lista de ComplaintRaw normalizadas
        """
        data = self._load_json("phone_transcripts.json")
        complaints = []

        for item in data.get("transcripts", []):
            complaint = ComplaintRaw(
                id=str(uuid.uuid4()),
                external_id=item["external_id"],
                source=ComplaintSource.PHONE,
                company_name="TechNova Store",
                title=item["title"],
                description=item["transcript"],
                consumer_name=item["consumer_name"],
                consumer_contact=item.get("consumer_phone"),
                created_at=self._parse_datetime(item["created_at"]),
                channel="Telefone",
                city=item.get("city"),
                state=item.get("state"),
                status=item.get("status", "Aberta"),
            )
            complaints.append(complaint)

        return complaints

    def load_support_emails(self) -> List[ComplaintRaw]:
        """
        Carrega emails de suporte.

        Returns:
            Lista de ComplaintRaw normalizadas
        """
        data = self._load_json("support_emails.json")
        complaints = []

        for item in data.get("emails", []):
            complaint = ComplaintRaw(
                id=str(uuid.uuid4()),
                external_id=item["external_id"],
                source=ComplaintSource.EMAIL,
                company_name="TechNova Store",
                title=item["subject"],
                description=item["body"],
                consumer_name=item["consumer_name"],
                consumer_contact=item.get("from"),
                created_at=self._parse_datetime(item["created_at"]),
                channel="Email",
                city=item.get("city"),
                state=item.get("state"),
                status=item.get("status", "Não Lida"),
            )
            complaints.append(complaint)

        return complaints

    def load_all_complaints(
        self,
        sources: Optional[List[ComplaintSource]] = None
    ) -> List[ComplaintRaw]:
        """
        Carrega reclamações de todas as fontes.

        Args:
            sources: Filtro opcional de fontes

        Returns:
            Lista unificada de ComplaintRaw
        """
        all_complaints: List[ComplaintRaw] = []

        source_loaders = {
            ComplaintSource.RECLAME_AQUI: self.load_reclame_aqui,
            ComplaintSource.JIRA: self.load_jira_issues,
            ComplaintSource.CHAT: self.load_chat_transcripts,
            ComplaintSource.WHATSAPP: self.load_chat_transcripts,
            ComplaintSource.PHONE: self.load_phone_transcripts,
            ComplaintSource.EMAIL: self.load_support_emails,
        }

        if sources:
            for source in sources:
                if source in source_loaders:
                    all_complaints.extend(source_loaders[source]())
        else:
            all_complaints.extend(self.load_reclame_aqui())
            all_complaints.extend(self.load_jira_issues())
            all_complaints.extend(self.load_chat_transcripts())
            all_complaints.extend(self.load_phone_transcripts())
            all_complaints.extend(self.load_support_emails())

        return all_complaints

    def load_teams(self) -> List[TeamInfo]:
        """
        Carrega definições de times.

        Returns:
            Lista de TeamInfo
        """
        data = self._load_json("teams.json")
        teams = []

        for item in data.get("teams", []):
            team = TeamInfo(
                id=item["id"],
                name=item["name"],
                email=item["email"],
                manager=item["manager"],
                description=item["description"],
                responsibilities=item["responsibilities"],
                categories=item["categories"],
                sla_hours=item["sla_hours"],
                example_cases=item["example_cases"],
            )
            teams.append(team)

        return teams

    def get_complaint_by_id(self, external_id: str) -> Optional[ComplaintRaw]:
        """
        Busca reclamação por ID externo.

        Args:
            external_id: ID externo da reclamação

        Returns:
            ComplaintRaw ou None se não encontrado
        """
        all_complaints = self.load_all_complaints()
        for complaint in all_complaints:
            if complaint.external_id == external_id:
                return complaint
        return None

    def get_stats(self) -> Dict[str, Any]:
        """
        Retorna estatísticas das reclamações mock.

        Returns:
            Dicionário com contagens por fonte
        """
        return {
            "reclame_aqui": len(self.load_reclame_aqui()),
            "jira": len(self.load_jira_issues()),
            "chat": len(self.load_chat_transcripts()),
            "phone": len(self.load_phone_transcripts()),
            "email": len(self.load_support_emails()),
            "total": len(self.load_all_complaints()),
        }

    def clear_cache(self) -> None:
        """Limpa o cache de dados."""
        self._cache.clear()


# Factory function
_loader: Optional[MockDataLoader] = None


def get_data_loader() -> MockDataLoader:
    """
    Factory function para obter o loader.

    Returns:
        Instância do MockDataLoader
    """
    global _loader
    if _loader is None:
        _loader = MockDataLoader()
    return _loader
