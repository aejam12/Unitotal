import streamlit as st
import cv2
import numpy as np
import pandas as pd
import face_recognition
import json
from datetime import datetime, date
from supabase import create_client, Client

# Conexión a la base de datos Supabase
@st.cache_resource
def init_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()

st.set_page_config(page_title="Control Asistencia Web", layout="wide")
st.title("📌 Sistema Web de Asistencia Facial")

menu = st.sidebar.selectbox("Navegación", ["Marcar Asistencia", "Gestión de Trabajadores", "Exportar Reportes"])

# Función para obtener rostros desde la BD
def obtener_trabajadores():
    res = supabase.table("trabajadores").select("*").execute()
    encodings = []
    ids = []
    nombres = []
    for row in res.data:
        encodings.append(np.array(json.loads(row["encoding"])))
        ids.append(row["id"])
        nombres.append(row["nombre"])
    return encodings, ids, nombres

# ----------------------------------------------------
# 1. MARCAR ASISTENCIA
# ----------------------------------------------------
if menu == "Marcar Asistencia":
    st.subheader("📷 Registro de Asistencia")
    tipo = st.radio("Acción:", ["hora_entrada", "inicio_descanso", "fin_descanso", "hora_salida"], horizontal=True)
    img_buffer = st.camera_input("Enfoca tu rostro frente a la cámara")

    if img_buffer:
        bytes_data = img_buffer.getvalue()
        cv2_img = cv2.imdecode(np.frombuffer(bytes_data, np.uint8), cv2.IMREAD_COLOR)
        rgb_img = cv2.cvtColor(cv2_img, cv2.COLOR_BGR2RGB)

        encodings_db, ids_db, nombres_db = obtener_trabajadores()
        rostros_capturados = face_recognition.face_encodings(rgb_img)

        if not rostros_capturados:
            st.error("No se detectó un rostro claro.")
        else:
            coincidencias = face_recognition.compare_faces(encodings_db, rostros_capturados[0], tolerance=0.5)
            if True in coincidencias:
                idx = coincidencias.index(True)
                emp_id = ids_db[idx]
                emp_nombre = nombres_db[idx]
                fecha_hoy = str(date.today())
                hora_actual = datetime.now().strftime("%H:%M:%S")

                # Consultar si existe registro hoy
                res = supabase.table("asistencias").select("*").eq("trabajador_id", emp_id).eq("fecha", fecha_hoy).execute()

                if len(res.data) == 0:
                    data = {
                        "trabajador_id": emp_id,
                        "nombre": emp_nombre,
                        "fecha": fecha_hoy,
                        tipo: hora_actual
                    }
                    supabase.table("asistencias").insert(data).execute()
                else:
                    supabase.table("asistencias").update({tipo: hora_actual}).eq("id", res.data[0]["id"]).execute()

                st.success(f"✅ Registro exitoso: {emp_nombre} ({tipo.replace('_', ' ').title()}) - {hora_actual}")
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
                bytes_data = foto.getvalue()
                cv2_img = cv2.imdecode(np.frombuffer(bytes_data, np.uint8), cv2.IMREAD_COLOR)
                rgb_img = cv2.cvtColor(cv2_img, cv2.COLOR_BGR2RGB)
                encs = face_recognition.face_encodings(rgb_img)

                if encs:
                    encoding_str = json.dumps(encs[0].tolist())
                    supabase.table("trabajadores").insert({
                        "id": tid,
                        "nombre": tnombre,
                        "encoding": encoding_str
                    }).execute()
                    st.success("Empleado registrado correctamente.")
                else:
                    st.error("No se detectó un rostro claro.")

    with tab2:
        encodings_db, ids_db, nombres_db = obtener_trabajadores()
        if ids_db:
            opciones = [f"{ids_db[i]} - {nombres_db[i]}" for i in range(len(ids_db))]
            seleccion = st.selectbox("Seleccionar empleado:", opciones)
            if st.button("Eliminar"):
                target_id = seleccion.split(" - ")[0]
                supabase.table("trabajadores").delete().eq("id", target_id).execute()
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

        archivo_excel = "asistencia.xlsx"
        df.to_excel(archivo_excel, index=False, engine="openpyxl")

        with open(archivo_excel, "rb") as f:
            st.download_button("📥 Descargar Excel", f, file_name="reporte_asistencia.xlsx")