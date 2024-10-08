import { Button } from '@mui/material';
import Box from '@mui/material/Box';
import * as React from 'react';
import Typography from '@mui/material/Typography';
import Logo from '../../assets/Logo.png';
import RegisterImg from '../../assets/ImagenRegister.png';
import './LoginStyle.css';
import { FormLogin } from '../../components';
import { useNavigate } from 'react-router-dom';  

export const Login: React.FC = () => {
    const navigate = useNavigate();  
  
    const handleRegister = () => {
        navigate('/register');  
    };
    const handleHome = ()=> {
        navigate('/home');  
    }

    return (
        <>
            <Box component='section' className='contenedorRegister'>
                <Box
                    component="form"
                    noValidate
                    autoComplete="off"
                    className='ContenedorFormularioLogin'
                >
                    <img src={Logo} alt="Logo" style={{ width: "262px", height: "146px" }} />
                    

                    <Box component="section" className='Formulario'>
                        <FormLogin /> 

                        <Box mt={3}>
                            <Box component="section" className='BotonesContenedorLogin'>
                                <Button variant="contained" onClick={handleHome}>Ingresar</Button>
                                
                                
                                <Button variant="contained" onClick={handleRegister}>
                                    Registrarte
                                </Button>
                            </Box>
                        </Box>
                    </Box>
                </Box>

                <Box component="section" className='contenedorImg'>
                    <img src={RegisterImg} alt="Imagen de registro" style={{ width: "612px", height: "402px" }} />
                </Box>
            </Box>
        </>
    );
};
