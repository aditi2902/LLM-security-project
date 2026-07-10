"""
TrustLens — SQLite persistent storage layer
Replaces flat JSON files with a proper relational database.
Tables:
  trust_events   — every query processed (ingress + egress audit trail)
  attack_records — every red team attack result
  suggestion_cache — cached LLM suggestions, keyed by attack text hash
"""

import hashlib
import os
from datetime import datetime, timezone
from sqlalchemy import (
    create_engine, Column, String, Integer, Float, Boolean,
    DateTime, Text, JSON, func
)
from sqlalchemy.orm import declarative_base, sessionmaker

# DB stored alongside the backend code
DB_PATH = os.path.join(os.path.dirname(__file__), "trustlens.db")
ENGINE = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=ENGINE, autoflush=False, autocommit=False)
Base = declarative_base()


# ─── Models ─────────────────────────────────────────────────────────────────

class TrustEvent(Base):
    """Full audit trail for every prompt processed by TrustLens (UI or proxy)."""
    __tablename__ = "trust_events"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    created_at       = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    source           = Column(String(32), default="ui")        # "ui" | "proxy"
    raw_prompt       = Column(Text,    nullable=False)
    intent           = Column(String(32), nullable=True)       # WEB | CHAT
    ingress_safe     = Column(Boolean, default=True)
    ingress_reason   = Column(Text,    nullable=True)
    ingress_risk     = Column(Float,   default=0.0)
    attack_type      = Column(String(64), nullable=True)
    content_risk     = Column(Float,   default=0.0)
    egress_safe      = Column(Boolean, default=True)
    egress_reason    = Column(Text,    nullable=True)
    blocked          = Column(Boolean, default=False)
    model_used       = Column(String(64), nullable=True)
    latency_ms       = Column(Integer, nullable=True)
    client_ip        = Column(String(64), nullable=True)
    country          = Column(String(128), nullable=True)
    country_code     = Column(String(8), nullable=True)
    latitude         = Column(Float, nullable=True)
    longitude        = Column(Float, nullable=True)
    vulnerability_type = Column(String(64), nullable=True)


class AttackRecord(Base):
    """One row per attack attempt from a red team wave."""
    __tablename__ = "attack_records"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    created_at     = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    attack_text    = Column(Text,    nullable=False)
    category       = Column(String(64),  default="UNKNOWN")
    technique      = Column(Text,    nullable=True)
    status         = Column(String(16),  nullable=False)    # BYPASSED | BLOCKED
    model_used     = Column(String(64),  default="groq")
    risk_score     = Column(Float,   default=0.0)
    block_reason   = Column(Text,    nullable=True)
    attack_type_detected = Column(String(64), nullable=True)
    client_ip        = Column(String(64), nullable=True)
    country          = Column(String(128), nullable=True)
    country_code     = Column(String(8), nullable=True)
    latitude         = Column(Float, nullable=True)
    longitude        = Column(Float, nullable=True)


class SuggestionCache(Base):
    """Cached LLM suggestions for a given attack (keyed by SHA256 of attack text)."""
    __tablename__ = "suggestion_cache"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    created_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    attack_hash  = Column(String(64), unique=True, nullable=False, index=True)
    attack_text  = Column(Text,   nullable=False)
    suggestions  = Column(JSON,   nullable=False)   # list of {title, description, priority}


class LearnedRule(Base):
    """Dynamically learned detection rules from bypassed red team attacks."""
    __tablename__ = "learned_rules"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    created_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    attack_hash  = Column(String(64), unique=True, nullable=False, index=True)
    attack_text  = Column(Text,   nullable=False)
    rule_text    = Column(Text,   nullable=False)
    category     = Column(String(64), nullable=True)
    approved     = Column(Boolean, default=False)


# ─── Init ────────────────────────────────────────────────────────────────────

def init_db():
    """Create all tables if they don't exist. Called at startup."""
    Base.metadata.create_all(bind=ENGINE)
    print("TrustLens DB initialised at:", DB_PATH)


# ─── Write helpers ───────────────────────────────────────────────────────────

def db_log_trust_event(
    raw_prompt: str,
    source: str = "ui",
    intent: str | None = None,
    ingress_safe: bool = True,
    ingress_reason: str | None = None,
    ingress_risk: float = 0.0,
    attack_type: str | None = None,
    content_risk: float = 0.0,
    egress_safe: bool = True,
    egress_reason: str | None = None,
    blocked: bool = False,
    model_used: str | None = None,
    latency_ms: int | None = None,
    client_ip: str | None = None,
    country: str | None = None,
    country_code: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    vulnerability_type: str | None = None,
) -> int:
    """Insert a trust event row and return its ID."""
    db = SessionLocal()
    try:
        ev = TrustEvent(
            raw_prompt=raw_prompt, source=source, intent=intent,
            ingress_safe=ingress_safe, ingress_reason=ingress_reason,
            ingress_risk=ingress_risk, attack_type=attack_type,
            content_risk=content_risk, egress_safe=egress_safe,
            egress_reason=egress_reason, blocked=blocked,
            model_used=model_used, latency_ms=latency_ms,
            client_ip=client_ip, country=country, country_code=country_code,
            latitude=latitude, longitude=longitude, vulnerability_type=vulnerability_type,
        )
        db.add(ev)
        db.commit()
        db.refresh(ev)
        return ev.id
    finally:
        db.close()


def db_log_attack(
    attack_text: str,
    category: str,
    technique: str,
    status: str,
    security_response: dict,
    model_used: str = "groq",
    client_ip: str | None = None,
    country: str | None = None,
    country_code: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> int:
    """Insert an attack record row and return its ID."""
    db = SessionLocal()
    try:
        rec = AttackRecord(
            attack_text=attack_text,
            category=category,
            technique=technique,
            status=status,
            model_used=model_used,
            risk_score=security_response.get("risk_score", 0.0),
            block_reason=security_response.get("reason"),
            attack_type_detected=security_response.get("attack_type"),
            client_ip=client_ip,
            country=country,
            country_code=country_code,
            latitude=latitude,
            longitude=longitude,
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        return rec.id
    finally:
        db.close()


def db_get_or_set_suggestions(attack_text: str, suggestions: list | None = None):
    """Return cached suggestions for an attack, or store new ones."""
    h = hashlib.sha256(attack_text.encode()).hexdigest()
    db = SessionLocal()
    try:
        cached = db.query(SuggestionCache).filter_by(attack_hash=h).first()
        if cached:
            return cached.suggestions
        if suggestions is not None:
            row = SuggestionCache(attack_hash=h, attack_text=attack_text, suggestions=suggestions)
            db.add(row)
            db.commit()
        return suggestions
    finally:
        db.close()


# ─── Analytics read helpers ───────────────────────────────────────────────────

def db_get_overview() -> dict:
    """Aggregate stats for the Analytics dashboard."""
    db = SessionLocal()
    try:
        # Trust events stats
        total_queries   = db.query(func.count(TrustEvent.id)).scalar() or 0
        blocked_ingress = db.query(func.count(TrustEvent.id)).filter(TrustEvent.blocked == True).scalar() or 0
        block_rate      = round(blocked_ingress / total_queries * 100, 1) if total_queries else 0.0

        # Attack stats
        total_attacks  = db.query(func.count(AttackRecord.id)).scalar() or 0
        bypassed_count = db.query(func.count(AttackRecord.id)).filter(AttackRecord.status == "BYPASSED").scalar() or 0
        blocked_count  = db.query(func.count(AttackRecord.id)).filter(AttackRecord.status == "BLOCKED").scalar() or 0
        bypass_rate    = round(bypassed_count / total_attacks * 100, 1) if total_attacks else 0.0
        security_score = round(max(0, 100 - bypass_rate * 0.8 - block_rate * 0.2), 1)

        # Last 7 days bypass trend (daily bypass rate)
        from sqlalchemy import text
        rows = db.execute(text("""
            SELECT date(created_at) as day,
                   COUNT(*) as total,
                   SUM(CASE WHEN status = 'BYPASSED' THEN 1 ELSE 0 END) as bypassed
            FROM attack_records
            WHERE created_at >= datetime('now', '-7 days')
            GROUP BY day
            ORDER BY day ASC
        """)).fetchall()

        trend = [
            {
                "date": r[0],
                "total": r[1],
                "bypassed": r[2],
                "bypass_rate": round(r[2] / r[1] * 100, 1) if r[1] else 0.0,
            }
            for r in rows
        ]

        # Attack category breakdown
        cat_rows = db.execute(text("""
            SELECT category, COUNT(*) as cnt,
                   SUM(CASE WHEN status = 'BYPASSED' THEN 1 ELSE 0 END) as bypassed
            FROM attack_records
            GROUP BY category
            ORDER BY cnt DESC
        """)).fetchall()

        categories = [
            {"category": r[0], "total": r[1], "bypassed": r[2], "blocked": r[1] - r[2]}
            for r in cat_rows
        ]

        # Recent attacks (last 10)
        recent = db.query(AttackRecord).order_by(AttackRecord.created_at.desc()).limit(10).all()
        recent_attacks = [
            {
                "id": a.id,
                "created_at": a.created_at.isoformat(),
                "category": a.category,
                "status": a.status,
                "preview": a.attack_text[:80] + ("..." if len(a.attack_text) > 80 else ""),
            }
            for a in recent
        ]

        return {
            "security_score": security_score,
            "total_queries": total_queries,
            "blocked_ingress": blocked_ingress,
            "block_rate": block_rate,
            "total_attacks": total_attacks,
            "bypassed_count": bypassed_count,
            "blocked_count": blocked_count,
            "bypass_rate": bypass_rate,
            "trend": trend,
            "categories": categories,
            "recent_attacks": recent_attacks,
        }
    finally:
        db.close()


def db_get_attacks(limit: int = 100, status: str | None = None) -> list:
    """Return attack records as dicts, newest first."""
    db = SessionLocal()
    try:
        q = db.query(AttackRecord).order_by(AttackRecord.created_at.desc())
        if status:
            q = q.filter(AttackRecord.status == status.upper())
        rows = q.limit(limit).all()
        return [
            {
                "timestamp": r.created_at.isoformat(),
                "attack_text": r.attack_text,
                "category": r.category,
                "technique": r.technique or "",
                "status": r.status,
                "model_used": r.model_used,
                "security_response": {
                    "safe": r.status != "BYPASSED",
                    "risk_score": r.risk_score,
                    "reason": r.block_reason,
                    "attack_type": r.attack_type_detected,
                },
            }
            for r in rows
        ]
    finally:
        db.close()


def db_add_learned_rule(attack_text: str, rule_text: str, category: str | None = None, approved: bool = False) -> bool:
    """Store a newly learned rule from a bypassed attack, ignoring duplicates."""
    h = hashlib.sha256(attack_text.encode()).hexdigest()
    db = SessionLocal()
    try:
        # Check if already exists
        exists = db.query(LearnedRule).filter_by(attack_hash=h).first()
        if exists:
            return False
        
        row = LearnedRule(
            attack_hash=h,
            attack_text=attack_text,
            rule_text=rule_text,
            category=category,
            approved=approved
        )
        db.add(row)
        db.commit()
        return True
    except Exception as e:
        print(f"Error adding learned rule: {e}")
        return False
    finally:
        db.close()


def db_get_learned_rules(limit: int = 10) -> list:
    """Return the most recently approved security rules."""
    db = SessionLocal()
    try:
        rows = db.query(LearnedRule).filter(LearnedRule.approved == True).order_by(LearnedRule.created_at.desc()).limit(limit).all()
        return [
            {
                "id": r.id,
                "attack_text": r.attack_text,
                "rule_text": r.rule_text,
                "category": r.category or "UNKNOWN",
                "created_at": r.created_at.isoformat(),
                "approved": r.approved,
            }
            for r in rows
        ]
    finally:
        db.close()


def db_get_pending_rules(limit: int = 20) -> list:
    """Return pending security rules awaiting approval."""
    db = SessionLocal()
    try:
        rows = db.query(LearnedRule).filter(LearnedRule.approved == False).order_by(LearnedRule.created_at.desc()).limit(limit).all()
        return [
            {
                "id": r.id,
                "attack_text": r.attack_text,
                "rule_text": r.rule_text,
                "category": r.category or "UNKNOWN",
                "created_at": r.created_at.isoformat(),
                "approved": r.approved,
            }
            for r in rows
        ]
    finally:
        db.close()


def db_approve_rule(rule_id: int) -> bool:
    """Approve a security rule to activate it in the active prompt security evaluation."""
    db = SessionLocal()
    try:
        rule = db.query(LearnedRule).filter_by(id=rule_id).first()
        if rule:
            rule.approved = True
            db.commit()
            return True
        return False
    except Exception as e:
        print(f"Error approving rule: {e}")
        return False
    finally:
        db.close()


def db_get_threat_heatmap_data() -> dict:
    """Compile geolocation distribution, hourly peak trends, and vector breakdown."""
    db = SessionLocal()
    try:
        from sqlalchemy import text
        # 1. Geo distribution (from attack_records)
        geo_rows = db.execute(text("""
            SELECT country, country_code, latitude, longitude, COUNT(*) as attack_count
            FROM attack_records
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
            GROUP BY country, country_code, latitude, longitude
            ORDER BY attack_count DESC
        """)).fetchall()
        
        geo_distribution = [
            {
                "country": r[0],
                "country_code": r[1],
                "latitude": r[2],
                "longitude": r[3],
                "count": r[4],
            }
            for r in geo_rows
        ]
        
        # 2. Hourly peak trends (hour of created_at)
        hourly_rows = db.execute(text("""
            SELECT strftime('%H', created_at) as hr, COUNT(*) as cnt
            FROM attack_records
            GROUP BY hr
            ORDER BY hr ASC
        """)).fetchall()
        
        # Ensure we have all 24 hours represented
        hourly_map = {f"{i:02d}": 0 for i in range(24)}
        for r in hourly_rows:
            if r[0] is not None:
                # Could be string or int hour
                hr_str = f"{int(r[0]):02d}"
                if hr_str in hourly_map:
                    hourly_map[hr_str] = r[1]
                
        hourly_trends = [
            {"hour": f"{hr}:00", "count": count}
            for hr, count in sorted(hourly_map.items())
        ]
        
        # 3. Vector breakdown (category stats)
        vector_rows = db.execute(text("""
            SELECT category, COUNT(*) as cnt
            FROM attack_records
            GROUP BY category
            ORDER BY cnt DESC
        """)).fetchall()
        
        vector_breakdown = [
            {"category": r[0], "count": r[1]}
            for r in vector_rows
        ]
        
        return {
            "geo_distribution": geo_distribution,
            "hourly_trends": hourly_trends,
            "vector_breakdown": vector_breakdown
        }
    finally:
        db.close()
