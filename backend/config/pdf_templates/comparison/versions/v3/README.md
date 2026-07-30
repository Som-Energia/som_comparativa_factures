# Plantilla de comparativa v3

La v3 genera el document comercial aprovat de cinc pagines. Les pagines 1, 2, 4 i 5 provenen del PDF mestre i conserven els seus enllacos; la pagina 3 es genera amb les dades calculades de cada simulacio.

El PDF mestre i les fonts Outfit no es desen dins d'aquesta versio editable. La imatge Docker els prepara a `/seed-reference/reference` i l'entrypoint els copia a `/app/assets/reference` quan el volum d'assets no els conte.

No editeu `comparison-v3.pdf` al volum de produccio: actualitzar el disseny requereix una nova versio de plantilla i un PDF mestre aprovat.
