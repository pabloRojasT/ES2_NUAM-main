"""Crea datos de demostración: 2 corredoras, usuarios de cada perfil y calificaciones.

SOLO PARA DESARROLLO Y DEMOSTRACIÓN. Las contraseñas son públicas (están en este
archivo): nunca ejecutes este comando en un entorno real.
"""
from decimal import Decimal as D

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from calificaciones.models import Mercado, Origen
from calificaciones.services import guardar_calificacion
from cuentas.models import Corredora, Perfil

CLAVE_DEMO = "Demo-nuam-2026"

USUARIOS = [
    # usuario, nombre, corredora, rol
    ("admin.andina", "María P.", "Corredora Andina S.A.", Perfil.Rol.ADMIN),
    ("analista.andina", "Tomás R.", "Corredora Andina S.A.", Perfil.Rol.ANALISTA),
    ("auditor.andina", "Andrea V.", "Corredora Andina S.A.", Perfil.Rol.AUDITOR),
    ("analista.boreal", "Luis M.", "Corredora Boreal Ltda.", Perfil.Rol.ANALISTA),
]

CALIFICACIONES = [
    ("ACCION-ALFA", Mercado.ACCIONES, 1, Origen.CORREDOR, {8: 1000000, 9: 1000000, 10: 1000000}),
    ("ACCION-DELTA", Mercado.ACCIONES, 2, Origen.BOLSA, {8: 400000, 9: 350000, 10: 250000}),
    ("CFI-BETA", Mercado.CFI, 1, Origen.CORREDOR, {8: 500000, 9: 500000}),
    ("FM-GAMMA", Mercado.FONDOS_MUTUOS, 1, Origen.BOLSA, {c: 500000 for c in range(8, 14)}),
]


class Command(BaseCommand):
    help = "Crea corredoras, usuarios y calificaciones de demostración (solo desarrollo)."

    def handle(self, *args, **options):
        User = get_user_model()
        if User.objects.filter(username="admin.andina").exists():
            raise CommandError("Los datos de demostración ya existen.")

        for username, nombre, corredora_nombre, rol in USUARIOS:
            corredora, _ = Corredora.objects.get_or_create(nombre=corredora_nombre)
            usuario = User.objects.create_user(username=username, password=CLAVE_DEMO, first_name=nombre)
            Perfil.objects.create(usuario=usuario, corredora=corredora, rol=rol)

        analista = User.objects.get(username="analista.andina")
        for instrumento, mercado, secuencia, origen, montos in CALIFICACIONES:
            guardar_calificacion(
                analista,
                ejercicio=2025,
                mercado=mercado,
                instrumento=instrumento,
                secuencia=secuencia,
                origen=origen,
                montos={c: D(m) for c, m in montos.items()},
            )

        self.stdout.write(self.style.SUCCESS("Datos de demostración creados."))
        self.stdout.write(f"Usuarios: {', '.join(u[0] for u in USUARIOS)}")
        self.stdout.write(f"Contraseña de todos: {CLAVE_DEMO}")
