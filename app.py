import os
import json
import cv2
import numpy as np
import pandas as pd
import streamlit as st
from datetime import datetime, date
from supabase import create_client, Client
from deepface import DeepFace

# Conexión a Supabase
@st.cache_resource
def init_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()

st.set_page_config(page_title="Control Asistencia Web", layout="wide")
st.title("📌 Sistema Web de Asistencia Facial")

menu = st.sidebar.selectbox("Navegación", ["Marcar Asistencia", "Gestión de Trabajadores", "Exportar Reportes"])

# ----------------------------------------------------
# 1. MARCAR ASISTENCIA
# ----------------------------------------------------
if menu == "Marcar Asistencia":
    st.subheader("📷 Registro de Asistencia")
    tipo = st.radio("Acción:", ["hora_entrada", "inicio_descanso", "fin_descanso", "hora_salida"], horizontal=True)
    img_buffer = st.camera_input("Enfoca tu rostro frente a la cámara")

    if img_buffer:
        # Guardar imagen temporal
        with open("temp_foto.jpg", "wb") as f:
            f.write(img_buffer.getvalue())

        # Obtener trabajadores desde la BD
        res = supabase.table("trabajadores").select("*").execute()
        trabajadores = res.data

        reconocido = False
        emp_id = None
        emp_nombre = None

        # Comparar foto capturada con la lista guardada
        for emp in trabajadores:
            # Descargar imagen del bucket
            url_foto = emp.get("foto_url")
            if url_foto:
                try:
                    res_match = DeepFace.verify(
                        img1_path="temp_foto.jpg", 
                        img2_path=url_foto, 
                        model_name="VGG-Face", 
                        enforce_detection=False
                    )
                    if res_match.get("verified"):
                        reconocido = True
                        emp_id = emp["id"]
                        emp_nombre = emp["nombre"]
                        break
                except Exception:
                    continue

        # Limpiar archivo temporal
        if os.path.exists("temp_foto.jpg"):
            os.remove("temp_foto.jpg")

        if reconocido:
            fecha_hoy = str(date.today())
            hora_actual = datetime.now().strftime("%H:%M:%S")

            res_asistencia = supabase.table("asistencias").select("*").eq("trabajador_id", emp_id).eq("fecha", fecha_hoy).execute()

            if len(res_asistencia.data) == 0:
                supabase.table("asistencias").insert({
                    "trabajador_id": emp_id,
                    "nombre": emp_nombre,
                    "fecha": fecha_hoy,
                    tipo: hora_actual
                }).execute()
            else:
                supabase.table("asistencias").update({tipo: hora_actual}).eq("id", res_asistencia.data[0]["id"]).execute()

            st.success(f"✅ Registro exitoso: **{emp_nombre}** ({tipo.replace('_', ' ').title()}) a las {hora_actual}")
        else:
            st.error("❌ Rostro no reconocido.")

# ----------------------------------------------------
# 2. GESTIÓN DE TRABAJADORES
# ----------------------------------------------------
elif menu == "Gestión de Trabajadores":
    tab1, tab2 = st.tabs(["Agregar Trabajador", "Eliminar Trabajador"])

    with tab1:
        tid = st.text_input("ID / Documento")
        tnombre = st.text_input("Nombre Completo")
        foto = st.camera_input("Capturar Rostro")

        if st.button("Guardar"):
            if tid and tnombre and foto:
                nombre_archivo = f"{tid}.jpg"
                bytes_data = foto.getvalue()

                # Subir foto al bucket 'fotos' en Supabase Storage
                supabase.storage.from_("fotos").upload(
                    path=nombre_archivo, 
                    file=bytes_data, 
                    file_options={"content-type": "image/jpeg", "x-upsert": "true"}
                )

                # Obtener la URL pública
                public_url = supabase.storage.from_("fotos").get_public_url(nombre_archivo)

                # Insertar registro
                supabase.table("trabajadores").insert({
                    "id": tid,
                    "nombre": tnombre,
                    "foto_url": public_url
                }).execute()

                st.success(f"Empleado **{tnombre}** registrado correctamente.")
            else:
                st.warning("Completa todos los campos y toma la foto.")

    with tab2:
        res = supabase.table("trabajadores").select("*").execute()
        trabajadores = res.data
        if trabajadores:
            opciones = {f"{t['id']} - {t['nombre']}": t["id"] for t in trabajadores}
            seleccion = st.selectbox("Seleccionar empleado:", list(opciones.keys()))

            if st.button("Eliminar"):
                target_id = opciones[seleccion]
                supabase.table("trabajadores").delete().eq("id", target_id).execute()
                supabase.storage.from_("fotos").remove([f"{target_id}.jpg"])
                st.success("Empleado eliminado.")
                st.rerun()

# ----------------------------------------------------
# 3. EXPORTAR REPORTES
# ----------------------------------------------------
elif menu == "Exportar Reportes":
    res = supabase.table("asistencias").select("*").execute()
    if res.data:
        df = pd.DataFrame(res.data)
        st.dataframe(df, use_container_width=True)

        archivo_excel = "reporte_asistencia.xlsx"
        df.to_excel(archivo_excel, index=False, engine="openpyxl")

        with open(archivo_excel, "rb") as f:
            st.download_button("📥 Descargar Excel", f, file_name="asistencia.xlsx")
