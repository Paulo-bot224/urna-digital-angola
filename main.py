from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


APP_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = APP_DIR / "app" / "static"
DATA_DIR = Path(os.environ.get("URNA_DATA_DIR", APP_DIR / ".data"))
DATABASE_PATH = DATA_DIR / "urna.sqlite3"
GENESIS_HASH = "0" * 64
BALLOT_AAD = b"urna-digital-demo-v1"

rsa_private_key: rsa.RSAPrivateKey
rsa_public_key: rsa.RSAPublicKey
ledger_private_key: Ed25519PrivateKey
ledger_public_key: Ed25519PublicKey


class CandidateCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    party: str | None = Field(default=None, max_length=100)


class Candidate(BaseModel):
    candidate_id: str
    name: str
    party: str | None
    created_at: str


class VoteRequest(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=64)
    voter_token: str = Field(min_length=16, max_length=256)


class VoteReceipt(BaseModel):
    sequence: int
    block_hash: str
    message: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def save_private_key(path: Path, key: Any) -> None:
    serialized = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path.write_bytes(serialized)
    path.chmod(0o600)


def load_or_create_keys() -> None:
    global rsa_private_key, rsa_public_key
    global ledger_private_key, ledger_public_key

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    rsa_private_path = DATA_DIR / "encryption-private.pem"
    rsa_public_path = DATA_DIR / "encryption-public.pem"
    ledger_private_path = DATA_DIR / "ledger-signing-private.pem"
    ledger_public_path = DATA_DIR / "ledger-signing-public.pem"

    rsa_files = (rsa_private_path.exists(), rsa_public_path.exists())
    if rsa_files[0] != rsa_files[1]:
        raise RuntimeError("The RSA keypair is incomplete; restore or remove both key files.")
    if not rsa_files[0]:
        generated_rsa = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        save_private_key(rsa_private_path, generated_rsa)
        rsa_public_path.write_bytes(
            generated_rsa.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
    rsa_private_key = serialization.load_pem_private_key(
        rsa_private_path.read_bytes(), password=None
    )
    if not isinstance(rsa_private_key, rsa.RSAPrivateKey):
        raise RuntimeError("The configured encryption key is not an RSA private key.")
    rsa_public_key = rsa_private_key.public_key()

    ledger_files = (
        ledger_private_path.exists(),
        ledger_public_path.exists(),
    )
    if ledger_files[0] != ledger_files[1]:
        raise RuntimeError(
            "The ledger signing keypair is incomplete; restore or remove both key files."
        )
    if not ledger_files[0]:
        generated_signer = Ed25519PrivateKey.generate()
        save_private_key(ledger_private_path, generated_signer)
        ledger_public_path.write_bytes(
            generated_signer.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
    ledger_private_key = serialization.load_pem_private_key(
        ledger_private_path.read_bytes(), password=None
    )
    if not isinstance(ledger_private_key, Ed25519PrivateKey):
        raise RuntimeError("The configured ledger key is not an Ed25519 private key.")
    ledger_public_key = ledger_private_key.public_key()


def connect_db() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


@contextmanager
def database_session():
    connection = connect_db()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with database_session() as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS candidates (
                candidate_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                party TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS demo_tokens (
                token_hash TEXT PRIMARY KEY,
                issued_at TEXT NOT NULL,
                used INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS ledger (
                sequence INTEGER PRIMARY KEY,
                ciphertext TEXT NOT NULL,
                wrapped_key TEXT NOT NULL,
                nonce TEXT NOT NULL,
                previous_hash TEXT NOT NULL,
                block_hash TEXT NOT NULL,
                signature TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    load_or_create_keys()
    initialize_database()
    yield


app = FastAPI(
    title="Urna Digital — Demonstração",
    version="0.1.0",
    description=(
        "API educacional para demonstrar cadastro de candidatos, cédulas "
        "cifradas e auditoria de ledger. Não é adequada para eleições reais."
    ),
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/info", tags=["Sistema"])
def root() -> dict[str, str]:
    return {
        "name": "Urna Digital — Demonstração",
        "docs": "/docs",
        "notice": "Protótipo educacional; não usar em eleições oficiais.",
    }


@app.get("/healthz", tags=["Sistema"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/summary", tags=["Sistema"])
def get_summary() -> dict[str, Any]:
    with database_session() as connection:
        candidate_count = connection.execute(
            "SELECT COUNT(*) FROM candidates"
        ).fetchone()[0]

    audit = audit_ledger()
    records = audit["records"]
    return {
        "candidate_count": candidate_count,
        "votes_count": audit["blocks"],
        "chain_valid": audit["chain_valid"],
        "last_block_hash": records[-1]["block_hash"] if records else None,
    }


@app.post(
    "/candidates",
    response_model=Candidate,
    status_code=status.HTTP_201_CREATED,
    tags=["Candidatos"],
)
def create_candidate(payload: CandidateCreate) -> Candidate:
    candidate = Candidate(
        candidate_id=str(uuid4()),
        name=payload.name.strip(),
        party=payload.party.strip() if payload.party else None,
        created_at=utc_now(),
    )
    if len(candidate.name) < 2:
        raise HTTPException(status_code=422, detail="O nome precisa ter ao menos 2 caracteres.")

    with database_session() as connection:
        connection.execute(
            """
            INSERT INTO candidates (candidate_id, name, party, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                candidate.candidate_id,
                candidate.name,
                candidate.party,
                candidate.created_at,
            ),
        )
    return candidate


@app.get("/candidates", response_model=list[Candidate], tags=["Candidatos"])
def list_candidates() -> list[Candidate]:
    with database_session() as connection:
        rows = connection.execute(
            "SELECT candidate_id, name, party, created_at FROM candidates ORDER BY name"
        ).fetchall()
    return [Candidate(**dict(row)) for row in rows]


@app.post("/voters/demo-token", status_code=status.HTTP_201_CREATED, tags=["Votação"])
def issue_demo_token() -> dict[str, str]:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with database_session() as connection:
        connection.execute(
            "INSERT INTO demo_tokens (token_hash, issued_at) VALUES (?, ?)",
            (token_hash, utc_now()),
        )
    return {
        "voter_token": token,
        "notice": "Token de teste: pode ser emitido sem verificação de identidade.",
    }


def encrypt_ballot(candidate_id: str) -> tuple[str, str, str]:
    ballot_key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    ciphertext = AESGCM(ballot_key).encrypt(
        nonce, canonical_json({"candidate_id": candidate_id}), BALLOT_AAD
    )
    wrapped_key = rsa_public_key.encrypt(
        ballot_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return (
        base64.b64encode(ciphertext).decode("ascii"),
        base64.b64encode(wrapped_key).decode("ascii"),
        base64.b64encode(nonce).decode("ascii"),
    )


def block_payload(
    sequence: int,
    ciphertext: str,
    wrapped_key: str,
    nonce: str,
    previous_hash: str,
    created_at: str,
) -> dict[str, Any]:
    return {
        "sequence": sequence,
        "ciphertext": ciphertext,
        "wrapped_key": wrapped_key,
        "nonce": nonce,
        "previous_hash": previous_hash,
        "created_at": created_at,
    }


@app.post(
    "/votes",
    response_model=VoteReceipt,
    status_code=status.HTTP_201_CREATED,
    tags=["Votação"],
)
def cast_vote(payload: VoteRequest) -> VoteReceipt:
    token_hash = hashlib.sha256(payload.voter_token.encode("utf-8")).hexdigest()
    ciphertext, wrapped_key, nonce = encrypt_ballot(payload.candidate_id)
    created_at = utc_now()
    connection = connect_db()
    try:
        connection.execute("BEGIN IMMEDIATE")
        candidate = connection.execute(
            "SELECT candidate_id FROM candidates WHERE candidate_id = ?",
            (payload.candidate_id,),
        ).fetchone()
        if candidate is None:
            raise HTTPException(status_code=404, detail="Candidato não encontrado.")

        token = connection.execute(
            "SELECT used FROM demo_tokens WHERE token_hash = ?", (token_hash,)
        ).fetchone()
        if token is None:
            raise HTTPException(status_code=401, detail="Token de demonstração inválido.")
        if token["used"]:
            raise HTTPException(
                status_code=409, detail="Este token já foi usado para votar."
            )

        latest = connection.execute(
            "SELECT sequence, block_hash FROM ledger ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        sequence = (latest["sequence"] + 1) if latest else 1
        previous_hash = latest["block_hash"] if latest else GENESIS_HASH
        payload_to_hash = block_payload(
            sequence, ciphertext, wrapped_key, nonce, previous_hash, created_at
        )
        block_hash = hashlib.sha256(canonical_json(payload_to_hash)).hexdigest()
        signature = base64.b64encode(
            ledger_private_key.sign(bytes.fromhex(block_hash))
        ).decode("ascii")

        connection.execute(
            """
            INSERT INTO ledger
                (sequence, ciphertext, wrapped_key, nonce, previous_hash,
                 block_hash, signature, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sequence,
                ciphertext,
                wrapped_key,
                nonce,
                previous_hash,
                block_hash,
                signature,
                created_at,
            ),
        )
        connection.execute(
            "UPDATE demo_tokens SET used = 1 WHERE token_hash = ?", (token_hash,)
        )
        connection.commit()
        return VoteReceipt(
            sequence=sequence,
            block_hash=block_hash,
            message="Voto cifrado e registrado no ledger de demonstração.",
        )
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


@app.get("/crypto/public-key", tags=["Criptografia"])
def get_public_keys() -> dict[str, str]:
    encryption_pem = rsa_public_key.public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    signing_pem = ledger_public_key.public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return {
        "encryption_algorithm": "RSA-3072-OAEP-SHA256 + AES-256-GCM",
        "encryption_public_key_pem": encryption_pem.decode("ascii"),
        "encryption_key_fingerprint_sha256": hashlib.sha256(encryption_pem).hexdigest(),
        "ledger_signature_algorithm": "Ed25519",
        "ledger_signing_public_key_pem": signing_pem.decode("ascii"),
    }


@app.get("/audit/ledger", tags=["Auditoria"])
def audit_ledger() -> dict[str, Any]:
    with database_session() as connection:
        rows = connection.execute(
            """
            SELECT sequence, ciphertext, wrapped_key, nonce, previous_hash,
                   block_hash, signature, created_at
            FROM ledger ORDER BY sequence
            """
        ).fetchall()

    expected_previous = GENESIS_HASH
    records: list[dict[str, Any]] = []
    chain_valid = True
    for expected_sequence, row in enumerate(rows, start=1):
        record = dict(row)
        block_data = block_payload(
            record["sequence"],
            record["ciphertext"],
            record["wrapped_key"],
            record["nonce"],
            record["previous_hash"],
            record["created_at"],
        )
        calculated_hash = hashlib.sha256(canonical_json(block_data)).hexdigest()
        link_valid = record["previous_hash"] == expected_previous
        content_valid = calculated_hash == record["block_hash"]
        sequence_valid = record["sequence"] == expected_sequence
        try:
            ledger_public_key.verify(
                base64.b64decode(record["signature"], validate=True),
                bytes.fromhex(calculated_hash),
            )
            signature_valid = True
        except (InvalidSignature, ValueError, TypeError):
            signature_valid = False

        record["valid"] = (
            link_valid and content_valid and sequence_valid and signature_valid
        )
        chain_valid = chain_valid and record["valid"]
        expected_previous = record["block_hash"]
        records.append(record)

    return {
        "chain_valid": chain_valid,
        "blocks": len(records),
        "records": records,
        "verification": "SHA-256 encadeado + assinatura Ed25519",
        "notice": (
            "A verificação demonstra integridade relativa aos arquivos locais; "
            "não substitui auditoria independente nem âncora externa."
        ),
    }


@app.get("/tally", tags=["Auditoria"])
def get_tally() -> dict[str, Any]:
    audit = audit_ledger()
    if not audit["chain_valid"]:
        raise HTTPException(
            status_code=409,
            detail="O ledger não passou na auditoria; a apuração foi bloqueada.",
        )

    with database_session() as connection:
        candidates = connection.execute(
            "SELECT candidate_id, name, party FROM candidates ORDER BY name"
        ).fetchall()
        ballots = connection.execute(
            "SELECT ciphertext, wrapped_key, nonce FROM ledger ORDER BY sequence"
        ).fetchall()

    totals = {
        row["candidate_id"]: {
            "candidate_id": row["candidate_id"],
            "name": row["name"],
            "party": row["party"],
            "votes": 0,
        }
        for row in candidates
    }
    for ballot in ballots:
        ballot_key = rsa_private_key.decrypt(
            base64.b64decode(ballot["wrapped_key"]),
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        plaintext = AESGCM(ballot_key).decrypt(
            base64.b64decode(ballot["nonce"]),
            base64.b64decode(ballot["ciphertext"]),
            BALLOT_AAD,
        )
        choice = json.loads(plaintext.decode("utf-8"))["candidate_id"]
        if choice not in totals:
            raise HTTPException(
                status_code=500, detail="O ledger contém uma cédula inválida."
            )
        totals[choice]["votes"] += 1

    return {
        "ballots_count": len(ballots),
        "results": list(totals.values()),
        "notice": "Apuração de demonstração; não representa resultado eleitoral oficial.",
    }
