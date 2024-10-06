import { Box, Button, Typography } from '@mui/material';
import React from 'react';
import './BotonesStyle.css';

interface BotonesModulosProps {
    text: string;
    imgSrc?: string; // Hacer que imgSrc sea opcional
    value?: string;
    subValue?: string;
    Fecha?:string;
    imgMedida?:string;
    onClick?: () => void;
}

export const BotonesModulos: React.FC<BotonesModulosProps> = ({
    text,
    imgSrc,
    value,
    subValue,
    Fecha,
    imgMedida,
    onClick,
}) => {
    return (
        <Box>
            <Button 
                variant="contained" 
                onClick={onClick} 
                className='BotonModulo'
                sx={{
                    padding: '50px',
                    marginTop:"25px",
                    borderRadius:"15px", 
                    width:"100%",
                    height:"30vh"
                }}
            >   
                <Typography variant="button">{text}</Typography>
                {imgSrc && (
                    <img src={imgSrc} alt={text} style={{ width: '145px', height: '156px', marginBottom: '8px' }} />
                )}
                {Fecha && <Typography variant="h6" align="center">{Fecha}</Typography>}
                {imgMedida && (
                    <img src={imgMedida} alt={text} style={{ width: '50px', height: '60px', marginBottom: '8px' }} />
                )}
                {value && <Typography variant="h4" align="center">{value}</Typography>}
                
                {subValue && <Typography variant="body2" align="center">{subValue}</Typography>}
            </Button>
        </Box>
    );
};
