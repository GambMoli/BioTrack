import * as React from 'react';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Paper from '@mui/material/Paper';
import TablePagination from '@mui/material/TablePagination';
import Typography from '@mui/material/Typography';
import Box from '@mui/material/Box';

function createData(
  name: string,
  Edad: number,
  fecha: string,
  Medida: string,
  altura: number,
) {
  return { name, Edad, fecha, Medida, altura };
}

const rows = [
  createData('Pedro', 25, '2023-09-12', '97%', 1.75),
  createData('Ana', 30, '2023-08-30', '95%', 1.65),
  createData('Luis', 28, '2023-09-05', '98%', 1.80),
  createData('Maria', 32, '2023-09-18', '96%', 1.60),
  createData('Carlos', 27, '2023-09-10', '99%', 1.78),
];

export const TablaOxigeno: React.FC = () => {
  const [page, setPage] = React.useState(0);
  const [rowsPerPage, setRowsPerPage] = React.useState(5);

  const handleChangePage = (event: unknown, newPage: number) => {
    setPage(newPage);
  };

  const handleChangeRowsPerPage = (event: React.ChangeEvent<HTMLInputElement>) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  return (
    <>
     <Box sx={{ padding: '20px', textAlign: 'center' , backgroundColor:'white'  }}>
        <Typography variant="h4" gutterBottom>
          Historial de Oxigeno en sangre
        </Typography>
      </Box>
      <TableContainer component={Paper}>
        <Table sx={{ minWidth: 650 }} aria-label="simple table">
          <TableHead>
            <TableRow>
              <TableCell>Nombre</TableCell>
              <TableCell align="right">Edad</TableCell>
              <TableCell align="right">Fecha</TableCell>
              <TableCell align="right">Medida&nbsp;(%)</TableCell>
              <TableCell align="right">Altura</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows
              .slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage)
              .map((row) => (
                <TableRow key={row.name}>
                  <TableCell component="th" scope="row">
                    {row.name}
                  </TableCell>
                  <TableCell align="right">{row.Edad}</TableCell>
                  <TableCell align="right">{row.fecha}</TableCell>
                  <TableCell align="right">{row.Medida}</TableCell>
                  <TableCell align="right">{row.altura}</TableCell>
                </TableRow>
              ))}
          </TableBody>
        </Table>
      </TableContainer>

      {/* Personalización del color de fondo en TablePagination */}
      <TablePagination
        component="div"
        count={rows.length}
        page={page}
        onPageChange={handleChangePage}
        rowsPerPage={rowsPerPage}
        onRowsPerPageChange={handleChangeRowsPerPage}
        labelRowsPerPage="Filas por página"
        sx={{
          backgroundColor: '#f5f5f5', // Cambia este valor al color que quieras
        }}
      />
    </>
  );
};
