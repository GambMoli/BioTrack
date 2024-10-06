import { TextField } from '@mui/material';
import * as React from 'react';


export const FormLogin : React.FC = () =>(
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

      

    </>



)