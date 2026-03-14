import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import time

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="DCP-RECON Web", page_icon="🛰️", layout="wide")

st.title("🛰️ SISTEMA DCP-RECON v3.0")
st.subheader("Gestão Inteligente de Discipulados")

# --- CONEXÃO COM GOOGLE SHEETS ---
# No modo Web App, usamos um arquivo JSON de "Secrets" para não precisar logar toda hora
def conectar_google():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    # No Streamlit Cloud, as credenciais ficam guardadas em st.secrets
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    return gspread.authorize(creds)

# --- INTERFACE LATERAL (Configurações) ---
st.sidebar.header("Configurações do Sistema")
raio_km = st.sidebar.slider("Raio de Busca (KM)", 1, 50, 15)
nome_planilha_grupos = st.sidebar.text_input("Nome da Planilha de Grupos", "DCP_Grupos")
nome_planilha_forms = st.sidebar.text_input("Nome da Planilha de Respostas", "DCP_Respostas")

if st.button("🔍 PROCESSAR NOVO CANDIDATO"):
    with st.spinner("Conectando ao banco de dados e calculando rotas..."):
        try:
            gc = conectar_google()
            
            # Carregar dados
            df_grupos = pd.DataFrame(gc.open(nome_planilha_grupos).sheet1.get_all_records())
            df_candidatos = pd.DataFrame(gc.open(nome_planilha_forms).sheet1.get_all_records())
            
            # Pegar último candidato
            cand = df_candidatos.iloc[-1]
            
            # Localização com Geopy
            geolocator = Nominatim(user_agent="dcp_recon_webapp")
            loc_cand = geolocator.geocode(cand['Endereço Completo'])
            
            if loc_cand:
                ponto_cand = (loc_cand.latitude, loc_cand.longitude)
                sugestoes = []

                for _, grupo in df_grupos.iterrows():
                    # REGRAS DE NEGÓCIO (Lotação e Perfil)
                    if int(grupo['Membros Atuais']) < int(grupo['Capacidade Máxima']):
                        # Lógica de match de perfil (Homens/Mulheres/Misto/Casais)
                        # ... (mesma lógica anterior)
                        
                        loc_g = geolocator.geocode(grupo['Endereço'])
                        if loc_g:
                            d = geodesic(ponto_cand, (loc_g.latitude, loc_g.longitude)).km
                            if d <= raio_km:
                                sugestoes.append({"Grupo": grupo['Nome do Grupo'], "Dist": d, "Lider": grupo['Líder']})
                
                # EXIBIÇÃO NO WEB APP
                if sugestoes:
                    top = sorted(sugestoes, key=lambda x: x['Dist'])[0]
                    st.success(f"### ✅ Sugestão encontrada para {cand['Nome Completo']}!")
                    col1, col2 = st.columns(2)
                    col1.metric("Grupo Sugerido", top['Grupo'])
                    col2.metric("Distância", f"{top['Dist']:.2f} km")
                    st.info(f"📞 **Líder responsável:** {top['Lider']}")
                else:
                    st.warning("Nenhum grupo compatível encontrado no raio selecionado.")
            else:
                st.error("Endereço do candidato não localizado pelo GPS.")
                
        except Exception as e:
            st.error(f"Erro de conexão: {e}")
