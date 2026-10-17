from django.db import DEFAULT_DB_ALIAS, connections

from .models import Registro


def instalar_bloqueos(sender=None, using=DEFAULT_DB_ALIAS, **kwargs):
    conexion = connections[using]
    if conexion.vendor != "sqlite":
        return
    tabla = Registro._meta.db_table
    if tabla not in conexion.introspection.table_names():
        return
    with conexion.cursor() as cursor:
        for evento in ("UPDATE", "DELETE"):
            cursor.execute(
                f"CREATE TRIGGER IF NOT EXISTS {tabla}_sin_{evento.lower()} "
                f"BEFORE {evento} ON {tabla} "
                f"BEGIN SELECT RAISE(ABORT, 'La bitácora es inalterable'); END;"
            )
