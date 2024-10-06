import { Box, Typography, Menu, MenuItem, IconButton, Button } from '@mui/material';
import React, { useState } from 'react';
import AccountCircleIcon from '@mui/icons-material/AccountCircle'; // Ícono de cuenta
import LogoBiotrack from '../../assets/LogoBiotrack.png'
import { useNavigate } from 'react-router-dom';

export const Header: React.FC = () => {
    // Estado para controlar la apertura del menú
    const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
    const open = Boolean(anchorEl);

    // Función para abrir el menú
    const handleMenu = (event: React.MouseEvent<HTMLElement>) => {
        setAnchorEl(event.currentTarget);
    };

    // Función para cerrar el menú
    const handleClose = () => {
        setAnchorEl(null);
    };

    // Función para cerrar sesión (puedes agregar la lógica aquí)
    const handleLogout = () => {
        handleClose();
        console.log("Cerrar sesión");
        // Aquí iría la lógica para cerrar sesión, como redirigir o limpiar el estado de autenticación.
    };
    const navigate = useNavigate(); // Inicializar useNavigate

    const BackHome = () => {
        navigate("/Home"); // Redirigir a /MedidorOxigeno
    };

    return (
        <>
            <Box component="header" style={{ backgroundColor: '#D9D9D9CC', opacity: "80%", display: "flex", justifyContent: "space-between", padding: "10px" }}>

                <Button  onClick={BackHome}><img src={LogoBiotrack} alt="LogoBiotrack"  style={{ marginLeft: "30px" , marginTop:"10px", height:"5vh", width:"76%"}} /></Button>
                {/* Botón para abrir el menú */}
                <IconButton
                    edge="end"
                    color="inherit"
                    onClick={handleMenu}
                >
                    <AccountCircleIcon fontSize="large" />
                </IconButton>

                {/* Menú desplegable */}
                <Menu
                    id="menu-appbar"
                    anchorEl={anchorEl}
                    anchorOrigin={{
                        vertical: 'top',
                        horizontal: 'right',
                    }}
                    keepMounted
                    transformOrigin={{
                        vertical: 'top',
                        horizontal: 'right',
                    }}
                    open={open}
                    onClose={handleClose}
                >
                    <MenuItem onClick={handleClose}>Mi perfil</MenuItem> {/* Opcional: agregar otras opciones */}
                    <MenuItem onClick={handleLogout}>Cerrar sesión</MenuItem>
                </Menu>
            </Box>
        </>
    );
};
