import { TextField,FormControl,InputLabel,Select,MenuItem,SelectChangeEvent } from '@mui/material';
import * as React from 'react';


export const FormRegister : React.FC = () =>(
    <>

        
        <TextField
            required
            id="outlined-required"
            label="Usuario"
            
            style={{width:"100%" ,marginBottom:"30px"}}/>

        <TextField
            required
            id="outlined-required"
            label="Contraseña"
            
            style={{width:"100%",marginBottom:"30px"}}/>

        <TextField
            required
            id="outlined-required"
            label="Confirmar contraseña"
           
            style={{width:"100%" ,marginBottom:"30px"}}/>

        <TextField
            required
            id="outlined-required"
            label="Altura"
            
            style={{width:"100%", marginBottom:"30px"}} />

        <TextField
            required
            id="outlined-required"
            label="Peso"
            
            style={{width:"100%"}} />

    </>



)
// Este es el segundo formulario que mostrarás después
export const SecondForm: React.FC = () => {
    const [Condicion, SetCondicion] = React.useState('');
    const [Fumas, setFumas] = React.useState('');
    const [ejerciio, setEjercicio] = React.useState('');
    const [medicamentos, setMedicamentos] = React.useState('');

    const handleChange = (event: SelectChangeEvent) => {
        SetCondicion(event.target.value as string);
    };
    const handleChange2 = (event: SelectChangeEvent) => {
        setFumas(event.target.value as string);
    };
    const handleChange3 = (event: SelectChangeEvent) => {
        setEjercicio(event.target.value as string);
    };
    const handleChange4 = (event: SelectChangeEvent) => {
        setMedicamentos(event.target.value as string);
    };
    return (
        <>
            <FormControl fullWidth>
                <InputLabel id="demo-simple-select-label">¿Tienes alguna condición médica relevante?</InputLabel>
                <Select
                    labelId="demo-simple-select-label"
                    id="demo-simple-select"
                    value={Condicion}
                    label="Age"
                    onChange={handleChange}
                    style={{ marginBottom:"30px"}}
                >
                    <MenuItem value={10}>Si</MenuItem>
                    <MenuItem value={20}>No</MenuItem>
                </Select>
            </FormControl>
            <FormControl fullWidth>
                <InputLabel id="demo-simple-select-label">¿Fumas actualmente?</InputLabel>
                <Select
                    labelId="demo-simple-select-label"
                    id="demo-simple-select"
                    value={Fumas}
                    label="Age"
                    onChange={handleChange2}
                    style={{ marginBottom:"30px"}}
                >
                    <MenuItem value={10}>Si</MenuItem>
                    <MenuItem value={20}>No</MenuItem>
                </Select>
            </FormControl>
            <FormControl fullWidth>
                <InputLabel id="demo-simple-select-label">¿Haces ejercicio regularmente?</InputLabel>
                <Select
                    labelId="demo-simple-select-label"
                    id="demo-simple-select"
                    value={ejerciio}
                    label="Age"
                    onChange={handleChange3}
                    style={{ marginBottom:"30px"}}
                >
                    <MenuItem value={10}>Si</MenuItem>
                    <MenuItem value={20}>No</MenuItem>
                </Select>
            </FormControl>
            <FormControl fullWidth>
                <InputLabel id="demo-simple-select-label">¿Tomas medicamentos que puedan afectar la frecuencia cardíaca o los niveles de oxígeno en sangre?</InputLabel>
                <Select
                    labelId="demo-simple-select-label"
                    id="demo-simple-select"
                    value={medicamentos}
                    label="Age"
                    onChange={handleChange4}
                >
                    <MenuItem value={10}>Si</MenuItem>
                    <MenuItem value={20}>No</MenuItem>
                </Select>
            </FormControl>

        </>
    );
};