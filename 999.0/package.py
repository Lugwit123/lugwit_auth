# -*- coding: utf-8 -*-

name = "lugwit_auth"
version = "999.0"
description = "Lugwit auth center (JWT/password/user tables) shared by apps"
authors = ["Lugwit Team"]

requires = [
    "python-3.12+<3.13",
    "Lugwit_Module",
]

build_command = False
cachable = True
relocatable = True


def commands():
    env.PYTHONPATH.prepend("{root}/src")
    env.LUGWIT_AUTH_ROOT = "{root}"

    alias("lugwit_auth_init_db", "python {root}/src/lugwit_auth/init_db.py")
    alias("lugwit_auth_seed_users", "python {root}/src/lugwit_auth/seed_users.py")
    alias("lugwit_auth_migrate_chatroom_users", "python {root}/src/lugwit_auth/migrate_chatroom_users.py")

