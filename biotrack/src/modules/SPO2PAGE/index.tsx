import * as React from 'react';
import { Box, Grid, Typography } from '@mui/material';
import { BotonesModulos, Header } from '../../components';
import Fondo from '../../assets/FondoPrincipalPage.jpg';
import imagenSrc from '../../assets/OxigenoSangre.png';
export const SPO2Page: React.FC = () => {

    return(
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
                <Grid container spacing={4} justifyContent="center" alignItems="center"> {/* Espaciado entre elementos */}
                    <Grid item xs={24} sm={6} md={3}>
                        <BotonesModulos
                            text="Tomar Medida SpO2"
                            imgMedida={imagenSrc}
                            value='97%'
                            subValue='Normal SpO2'
                            
                        />
                    </Grid>

                   
                </Grid>
                <Grid container spacing={4} justifyContent="center" alignItems="center" > 
                    <Grid item xs={12} sm={6} md={3}>
                        <BotonesModulos
                            text="Mas reciente"
                            Fecha='08/02/2024 13:58'
                            value="97%"
                            subValue='Normal SpO2'
                            
                        />
                    </Grid>

                    <Grid item xs={12} sm={6} md={3}>
                        <BotonesModulos
                            text="Mas Alto - Mas bajo"
                            value='97% - 98%'
                            Fecha='08/02/2024 13:58'
                            subValue='Normal SpO2'
                            
                        />
                    </Grid>
                </Grid>
            </Box>


        </Box>
            
    );
}