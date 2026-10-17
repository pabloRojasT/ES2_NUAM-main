from unittest import skipUnless

from django.db import DatabaseError, connection, transaction
from django.test import TestCase

from cuentas.testing import crear_corredora, crear_usuario

from .models import ErrorBitacoraInmutable, Registro
from .servicios import registrar


class BitacoraInalterableTests(TestCase):
    def setUp(self):
        self.corredora = crear_corredora()
        self.usuario = crear_usuario("ana", self.corredora)
        self.registro = registrar(
            self.usuario, Registro.Operacion.INGRESO, "ACCION-ALFA · sec. 1", detalle="creada"
        )

    def test_registrar_guarda_usuario_corredora_fecha_y_origen(self):
        self.assertEqual(self.registro.usuario, self.usuario)
        self.assertEqual(self.registro.usuario_nombre, "ana")
        self.assertEqual(self.registro.corredora, self.corredora)
        self.assertIsNotNone(self.registro.fecha)
        self.assertEqual(self.registro.origen, Registro.Origen.FORMULARIO)

    def test_no_se_puede_modificar_un_registro(self):
        self.registro.detalle = "cambiado"
        with self.assertRaises(ErrorBitacoraInmutable):
            self.registro.save()

    def test_no_se_puede_borrar_un_registro(self):
        with self.assertRaises(ErrorBitacoraInmutable):
            self.registro.delete()

    def test_no_se_pueden_alterar_en_masa(self):
        with self.assertRaises(ErrorBitacoraInmutable):
            Registro.objects.all().update(detalle="x")
        with self.assertRaises(ErrorBitacoraInmutable):
            Registro.objects.all().delete()
        with self.assertRaises(ErrorBitacoraInmutable):
            Registro.objects.bulk_update([self.registro], ["detalle"])

    @skipUnless(connection.vendor == "sqlite", "Los triggers se instalan solo en SQLite")
    def test_la_base_rechaza_update_y_delete_con_sql_directo(self):
        tabla = Registro._meta.db_table
        for sentencia in (f"UPDATE {tabla} SET detalle = 'x'", f"DELETE FROM {tabla}"):
            with self.subTest(sentencia=sentencia):
                with self.assertRaises(DatabaseError), transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(sentencia)
        self.assertEqual(Registro.objects.count(), 1)
        self.assertEqual(Registro.objects.get().detalle, "creada")

    def test_se_puede_seguir_agregando(self):
        registrar(self.usuario, Registro.Operacion.MODIFICACION, "ACCION-ALFA · sec. 1")
        self.assertEqual(Registro.objects.count(), 2)
