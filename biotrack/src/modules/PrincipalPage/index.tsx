import { Box, Grid, Typography } from '@mui/material';
import * as React from 'react';
import { useNavigate } from 'react-router-dom'; // Importar useNavigate
import './PrincipalStyle.css';
import { BotonesModulos, Header } from '../../components';
import imagenSrc from '../../assets/OxigenoSangre.png';
import Fondo from '../../assets/FondoPrincipalPage.jpg';
import Frecuencia from '../../assets/FrecuenciaCardiaca.png';

export const PrincipalPage: React.FC = () => {
    const navigate = useNavigate(); // Inicializar useNavigate

    const oxigenoSangreModulo = () => {
        navigate("/MedidorOxigeno"); // Redirigir a /MedidorOxigeno
    };

    const frecuenciaCardiacaModulo = () => {
       navigate("/MedidorFrecuencia");
    };
    const HistorialOxigeno=()=>{
        navigate("/HistorialO2");
    }
    const HistorialFC = ()=> {
        navigate("/HistorialFC");
    }

    return (
        <Box
            component="section"
            sx={{
                backgroundImage: `url(${Fondo})`,
                backgroundSize: 'cover',
                backgroundPosition: 'center',
                minHeight: '100vh',
                display: 'flex',
                flexDirection: 'column',
            }}
        >
            <Header />

            <Box className="GridContainer">
                <Grid container spacing={4} justifyContent="center" alignItems="center">
                    <Grid item xs={12} sm={6} md={3}>
                        <BotonesModulos
                            text="Tomar Medida SpO2"
                            imgSrc={imagenSrc}
                            value=''
                            subValue=''
                            onClick={oxigenoSangreModulo} // Asignar la función a onClick
                        />
                    </Grid>

                    <Grid item xs={12} sm={6} md={3}>
                        <BotonesModulos
                            text="Tomar Frecuencia Cardíaca"
                            imgSrc={Frecuencia}
                            value=''
                            subValue=''
                            onClick={frecuenciaCardiacaModulo}
                        />
                    </Grid>
                </Grid>

                {/* Segunda fila con los historiales */}
                <Grid container spacing={4} justifyContent="center" alignItems="center">
                    <Grid item xs={12} sm={6} md={3}>
                        <BotonesModulos
                            text="Ver Historial FC"
                            value="65lpm"
                            subValue='Normal LPM'
                            onClick={HistorialFC}
                        />
                    </Grid>

                    <Grid item xs={12} sm={6} md={3}>
                        <BotonesModulos
                            text="Ver Historial SpO2"
                            value='97%'
                            subValue='Normal SpO2'
                            onClick={HistorialOxigeno}
                        />
                    </Grid>
                </Grid>
            </Box>
        </Box>
    );
};
