#!/usr/bin/env python3
"""RENTDZ management CLI: migrate, seed, admin, serve, test, maintenance."""
from __future__ import annotations
import sys, getpass, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import db                                   # noqa: E402
from app.config import Config                        # noqa: E402


def cmd_migrate(args):
    fresh = "--fresh" in args
    db.migrate(fresh=fresh)
    from app.services import auth_service, settings_service
    from app.services.payment import seed_providers
    with db.transaction():
        auth_service.seed_roles()
        settings_service.seed_defaults()
        seed_providers()
    n = db.scalar("SELECT COUNT(*) FROM sqlite_master WHERE type='table'", (), 0)
    print(f"Base de données prête ({n} tables) → {Config.db_path()}")


def cmd_seed(args):
    if Config.APP_ENV == "production":
        print("Refusé : les données de démonstration sont interdites en production.")
        return 2
    db.migrate()
    from app.seeds import demo
    email = "admin@rentdz.dz"
    password = None
    for a in args:
        if a.startswith("--admin-email="):
            email = a.split("=", 1)[1]
        if a.startswith("--admin-password="):
            password = a.split("=", 1)[1]
    with db.transaction():
        result = demo.seed(admin_email=email, admin_password=password)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("\nComptes de démonstration (mot de passe commun : RentDZ2026!) :")
    for role, acc in result["accounts"].items():
        print(f"  {role:12} {acc['email']:32} {acc['password']}")


def cmd_purge_demo(args):
    db.migrate()
    from app.seeds import demo
    with db.transaction():
        print(json.dumps(demo.purge(), indent=2))


def cmd_createadmin(args):
    db.migrate()
    from app.services import auth_service as A
    from app.security import hash_password, now_str
    email = input("E-mail de l'administrateur : ").strip().lower()
    name = input("Nom complet : ").strip() or "Administrateur"
    pw = getpass.getpass("Mot de passe : ")
    pw2 = getpass.getpass("Confirmer : ")
    if pw != pw2:
        print("Les mots de passe ne correspondent pas.")
        return 2
    from app.security import password_problem
    problem = password_problem(pw)
    if problem:
        print(problem)
        return 2
    with db.transaction():
        A.seed_roles()
        existing = A.find_by_email(email)
        if existing:
            db.update("users", existing["id"], {"password_hash": hash_password(pw),
                                                "updated_at": now_str()})
            uid = existing["id"]
            print("Utilisateur existant : mot de passe mis à jour.")
        else:
            uid = db.insert("users", {
                "email": email, "password_hash": hash_password(pw), "full_name": name,
                "status": "active", "email_verified_at": now_str(),
                "created_at": now_str(), "updated_at": now_str()})
        A.grant_role(uid, "super_admin")
        A.grant_role(uid, "admin")
    print(f"Super administrateur prêt : {email}")


def cmd_serve(args):
    from app.http import serve
    serve()


def cmd_test(args):
    from tests.run_all import main as run_tests
    return run_tests(args)


def cmd_release_holds(args):
    db.migrate()
    from app.services.availability import release_expired_holds
    print(f"Réservations expirées libérées : {release_expired_holds()}")


def cmd_purge_documents(args):
    db.migrate()
    from app.services.document_service import purge_expired
    print(f"Documents supprimés (rétention) : {purge_expired('--dry-run' in args)}")


def cmd_flush_outbox(args):
    db.migrate()
    from app.services.notification_service import flush_outbox
    print(json.dumps(flush_outbox(), indent=2))


def cmd_check(args):
    db.migrate()
    print(f"Environnement : {Config.APP_ENV}   ·   Base : {Config.db_path()}")
    print("\nPréparation à la production :")
    ok = True
    for c in Config.production_readiness():
        mark = "OK  " if c["ok"] else "TODO"
        if not c["ok"]:
            ok = False
        print(f"  [{mark}] {c['check']}" + ("" if c["ok"] else f"\n         → {c['detail']}"))
    print("\nIntégrations :")
    for name, info in Config.integration_status().items():
        print(f"  {name:10} {info['provider']:22} {info['status']}")
        if info["status"] != "configured":
            print(f"             variables : {', '.join(info['vars'])}")
    print("\nDonnées :")
    for table in ("users", "rental_companies", "vehicles", "bookings", "payments", "documents"):
        print(f"  {table:18} {db.scalar(f'SELECT COUNT(*) FROM {table}', (), 0)}")
    return 0 if ok else 1


COMMANDS = {
    "migrate": cmd_migrate, "seed": cmd_seed, "purge-demo": cmd_purge_demo,
    "createadmin": cmd_createadmin, "serve": cmd_serve, "test": cmd_test,
    "release-holds": cmd_release_holds, "purge-documents": cmd_purge_documents,
    "flush-outbox": cmd_flush_outbox, "check": cmd_check,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("RENTDZ — commandes disponibles :\n")
        for name in COMMANDS:
            print(f"  python manage.py {name}")
        print("\nExemples :")
        print("  python manage.py migrate --fresh")
        print("  python manage.py seed")
        print("  python manage.py serve")
        print("  python manage.py test")
        sys.exit(1)
    sys.exit(COMMANDS[sys.argv[1]](sys.argv[2:]) or 0)
