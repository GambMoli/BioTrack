import * as React from 'react';
import { Header, TablaOxigeno } from '../../components';
import Fondo from '../../assets/FondoPrincipalPage.jpg';
import { Box, Grid, Typography } from '@mui/material';
import './HistorialStyle.css'
export const HistorialOxigeno: React.FC = () =>{
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
        <Box className="TablaContainer">
                    <TablaOxigeno></TablaOxigeno>
                   
        </Box>
       
</Box>  
    );

}