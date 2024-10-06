import { Button } from '@mui/material';
import Box from '@mui/material/Box';
import * as React from 'react';
import Typography from '@mui/material/Typography';
import Logo from '../../assets/Logo.png';
import RegisterImg from '../../assets/ImagenRegister.png';
import './RegisterStyle.css';
import { FormRegister, SecondForm } from '../../components';
import { useState } from 'react';

export const Register: React.FC = () => {
    // Estado para controlar qué formulario mostrar
    const [step, setStep] = useState(1);
    const [registro,setRegistro]=useState("");
    // Función para cambiar al siguiente formulario
    const handleNext = () => {
        setStep(step + 1);  // Cambia el estado al siguiente formulario
    };

    // Función para volver al formulario anterior
    const handleBack = () => {
        setStep(step - 1);  // Cambia el estado al formulario anterior
    };
    const Registro=()=>{
        setRegistro("Registro exitoso");
    }
    return (
        <>
            <Box component='section' className='contenedorRegister'>
                <Box
                    component="form"
                    noValidate
                    autoComplete="off"
                    className='ContenedorFormulario'
                >
                    <img src={Logo} alt="Logo" style={{ width: "262px", height: "146px" }} />
                    <Typography variant="h6" style={{ color: "#2254AA", fontSize: "32px", padding:"0px 30px" }}>
                        {step === 1 ? "Ingresa tus datos para empezar tu registro de salud" : "Ingresa tus datos de salud"}
                    </Typography>

                    <Box component="section" className='Formulario'>
           
                        {step === 1 ? <FormRegister /> : <SecondForm />}

                        <Box mt={3}>
                            {step === 1 ? (
                                <Button variant="contained" onClick={handleNext}>
                                    Siguiente
                                </Button>
                            ) : (
                                <>
                                <Box component="section"
                                className='BotonesContenedor'>
                                    <Button variant="contained" onClick={handleBack} >
                                        Atrás
                                    </Button>
                                    <Button variant="contained" onClick={Registro} >
                                        Registrarte
                                    </Button>
                                </Box>
                                </>
                            )}
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
