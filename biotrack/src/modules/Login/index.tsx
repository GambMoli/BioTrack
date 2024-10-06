import { Button } from '@mui/material';
import Box from '@mui/material/Box';
import * as React from 'react';
import Typography from '@mui/material/Typography';
import Logo from '../../assets/Logo.png';
import RegisterImg from '../../assets/ImagenRegister.png';
import './LoginStyle.css';
import { FormLogin } from '../../components';
import { useNavigate } from 'react-router-dom';  // Importa useNavigate

export const Login: React.FC = () => {
    const navigate = useNavigate();  // Crea una instancia del hook useNavigate
  
    // Función para manejar el click en "Registrarte"
    const handleRegister = () => {
        navigate('/register');  // Redirige a la ruta de registro
    };

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
                    <Typography variant="h6" style={{ color: "#2254AA", fontSize: "32px", padding: "0px 30px" }}>
                        {/* Puedes agregar un título o cualquier otro texto aquí */}
                    </Typography>

                    <Box component="section" className='Formulario'>
                        <FormLogin /> 

                        <Box mt={3}>
                            <Box component="section" className='BotonesContenedorLogin'>
                                <Button variant="contained">Ingresar</Button>
                                
                                
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
