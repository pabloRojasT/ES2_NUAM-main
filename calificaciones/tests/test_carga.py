from django.test import TestCase

from bitacora.models import Registro
from calificaciones import carga
from calificaciones.models import Calificacion, Origen
from cuentas.models import Perfil
from cuentas.testing import crear_corredora, crear_usuario

ENCABEZADO = "ejercicio,mercado,instrumento,secuencia,origen,monto_8,monto_9,monto_base"


def csv_de_prueba(invalidas=True):
    """100 filas. Si ``invalidas``: las filas 17, 42, 58 y 91 traen un error distinto cada una."""
    filas = [ENCABEZADO]
    for n in range(1, 101):
        fila = f"2025,Acciones,INS-{n:03d},1,corredor,400000,300000,1000000"
        if invalidas and n == 17:
            fila = "2025,CFI,INS-017,1,corredor,700000,700000,1000000"      # suma 1,4 > 1
        elif invalidas and n == 42:
            fila = "2025,Fondos Mutuos,,2,corredor,400000,300000,1000000"    # sin instrumento
        elif invalidas and n == 58:
            fila = "2025,Bonos,INS-058,1,corredor,400000,300000,1000000"     # mercado desconocido
        elif invalidas and n == 91:
            fila = "2025,CFI,INS-091,tres,corredor,400000,300000,1000000"    # secuencia no numérica
        filas.append(fila)
    return "\n".join(filas) + "\n"


class CargaMasivaTests(TestCase):
    def setUp(self):
        self.corredora = crear_corredora()
        self.analista = crear_usuario("ana", self.corredora, Perfil.Rol.ANALISTA)

    def test_la_vista_previa_distingue_validas_e_invalidas_con_su_motivo(self):
        filas = carga.leer_csv(csv_de_prueba(), self.corredora)
        con_error = {f.numero: f.error for f in filas if f.error}
        self.assertEqual(len(filas), 100)
        self.assertEqual(sorted(con_error), [17, 42, 58, 91])
        self.assertIn("RN1", con_error[17])
        self.assertIn("Instrumento", con_error[42])
        self.assertIn("Bonos", con_error[58])
        self.assertIn("secuencia", con_error[91])
        self.assertEqual(Calificacion.objects.count(), 0)  # la vista previa no guarda nada

    def test_carga_96_validas_y_rechaza_4_con_motivo(self):
        filas = carga.leer_csv(csv_de_prueba(), self.corredora)
        resultado = carga.ejecutar_carga(self.analista, filas, "calificaciones_2025.csv")
        self.assertEqual(resultado.nuevas, 96)
        self.assertEqual(len(resultado.rechazadas), 4)
        self.assertEqual(Calificacion.objects.count(), 96)

    def test_cargar_dos_veces_el_mismo_archivo_no_genera_duplicados(self):
        for _ in range(2):
            filas = carga.leer_csv(csv_de_prueba(), self.corredora)
            resultado = carga.ejecutar_carga(self.analista, filas, "calificaciones_2025.csv")
        self.assertEqual(Calificacion.objects.count(), 96)
        self.assertEqual(resultado.nuevas, 0)
        self.assertEqual(resultado.sin_cambios, 96)

    def test_una_carga_con_cambios_actualiza_por_llave(self):
        carga.ejecutar_carga(self.analista, carga.leer_csv(csv_de_prueba(False), self.corredora), "a.csv")
        modificado = csv_de_prueba(False).replace(
            "2025,Acciones,INS-005,1,corredor,400000,300000,1000000",
            "2025,Acciones,INS-005,1,corredor,500000,300000,1000000",
        )
        resultado = carga.ejecutar_carga(self.analista, carga.leer_csv(modificado, self.corredora), "b.csv")
        self.assertEqual(resultado.actualizadas, 1)
        self.assertEqual(resultado.sin_cambios, 99)
        self.assertEqual(Calificacion.objects.count(), 100)

    def test_toda_operacion_queda_en_la_bitacora(self):
        filas = carga.leer_csv(csv_de_prueba(), self.corredora)
        carga.ejecutar_carga(self.analista, filas, "calificaciones_2025.csv")
        self.assertEqual(Registro.objects.filter(operacion=Registro.Operacion.INGRESO).count(), 96)
        resumen = Registro.objects.get(operacion=Registro.Operacion.CARGA_MASIVA)
        self.assertEqual(resumen.registro, "calificaciones_2025.csv")
        self.assertIn("96 nuevas", resumen.detalle)
        self.assertIn("4 rechazadas", resumen.detalle)
        self.assertEqual(
            set(Registro.objects.filter(operacion=Registro.Operacion.INGRESO).values_list("origen", flat=True)),
            {Registro.Origen.CARGA_MASIVA},
        )

    def test_llave_repetida_dentro_del_archivo(self):
        texto = ENCABEZADO + "\n" + "\n".join(
            ["2025,Acciones,INS-001,1,corredor,400000,300000,1000000"] * 2
        )
        filas = carga.leer_csv(texto, self.corredora)
        self.assertEqual(filas[0].error, "")
        self.assertIn("Llave repetida", filas[1].error)

    def test_rn2_el_dato_de_bolsa_no_pisa_al_del_corredor(self):
        carga.ejecutar_carga(self.analista, carga.leer_csv(csv_de_prueba(False), self.corredora), "a.csv")
        texto = ENCABEZADO + "\n2025,Acciones,INS-001,1,bolsa,1,1,\n"
        filas = carga.leer_csv(texto, self.corredora)
        self.assertIn("RN2", filas[0].error)
        self.assertEqual(Calificacion.objects.get(instrumento="INS-001").origen, Origen.CORREDOR)

    def test_acepta_punto_y_coma_bom_y_sin_tildes_en_el_mercado(self):
        texto = (
            "﻿ejercicio;mercado;instrumento;secuencia;monto_8;monto_9\n"
            "2025;Cuotas de fondos de inversión;CFI-X;1;100;100\n"
        )
        filas = carga.leer_csv(texto, self.corredora)
        self.assertEqual(filas[0].error, "")
        self.assertEqual(filas[0].mercado_codigo, "CFI")

    def test_errores_del_archivo_completo(self):
        casos = {
            "vacío": "",
            "sin columnas obligatorias": "ejercicio,mercado\n2025,Acciones\n",
            "sin columnas de monto": "ejercicio,mercado,instrumento,secuencia\n2025,Acciones,X,1\n",
            "columna de monto fuera de rango": ENCABEZADO.replace("monto_9", "monto_99") + "\n",
            "sin filas": ENCABEZADO + "\n",
        }
        for nombre, texto in casos.items():
            with self.subTest(caso=nombre):
                with self.assertRaises(carga.ErrorArchivo):
                    carga.leer_csv(texto, self.corredora)
