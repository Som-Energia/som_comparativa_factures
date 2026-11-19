export const emailCopy = {
  ca: {
    locale: 'ca-ES', retailer: 'Comercialitzadora actual', beneficiaries: 'Accionistes',
    summary: 'Resum de la comparativa', concept: 'Concepte', days: 'dies',
    cost: 'Cost del període facturat', difference: 'Diferència', renewable: 'Origen de l’energia renovable certificada',
    nonprofit: 'Sense ànim de lucre', profits: 'Els beneficis són per a…', cooperative: 'La cooperativa',
    ocu: 'Valoració OCU', best: '🏆 La millor valorada', permanence: 'Permanència',
    reasonParts: { energy: 'del consum', power: 'de la potència', both: 'del consum i de la potència' },
    reason: (part, unfavorable) => unfavorable
      ? `La diferència de preu s’explica per un menor cost ${part} per part de la teva comercialitzadora actual; desconeixem si forma part d’una oferta temporal.`
      : `El principal motiu és que els preus ${part} que tens actualment són més elevats que els que apliquem a la cooperativa.`,
  },
  es: {
    locale: 'es-ES', retailer: 'Comercializadora actual', beneficiaries: 'Accionistas',
    summary: 'Resumen de la comparativa', concept: 'Concepto', days: 'días',
    cost: 'Coste del período facturado', difference: 'Diferencia', renewable: 'Origen de la energía renovable certificada',
    nonprofit: 'Sin ánimo de lucro', profits: 'Los beneficios son para…', cooperative: 'La cooperativa',
    ocu: 'Valoración OCU', best: '🏆 Mejor valorada', permanence: 'Permanencia',
    reasonParts: { energy: 'del consumo', power: 'de la potencia', both: 'del consumo y de la potencia' },
    reason: (part, unfavorable) => unfavorable
      ? `La diferencia de precio se explica por un menor coste ${part} en tu comercializadora actual; desconocemos si forma parte de una oferta temporal.`
      : `El principal motivo es que los precios ${part} que tienes actualmente son más elevados que los que aplicamos en la cooperativa.`,
  },
}

export function emailTemplate(savings, language) {
  const unfavorable = savings < 0
  if (language === 'es') {
    const result = savings > 0
      ? 'El resultado es favorable: el coste con Som Energia es inferior al de la factura actual.'
      : unfavorable
        ? 'El resultado es desfavorable: el coste con Som Energia es superior al de la factura actual.'
        : 'En esta simulación, el coste con Som Energia es igual al de la factura actual.'
    return {
      intro: `Hola,

¡Gracias por aportarnos los datos de tu consumo!

En el documento adjunto encontrarás el cálculo de cómo habría sido tu factura con la [tarifa períodos de Som Energia](https://www.somenergia.coop/es/tarifas-luz/domestico-periodos).

${result} A continuación verás el resumen:`,
      body: `En el documento encontrarás el detalle. Esta simulación solo es válida para esta factura y no es extrapolable al coste anual de la luz.

${unfavorable
    ? 'Sobre la otra opción que ofrecemos, la [tarifa indexada](https://www.somenergia.coop/es/tarifas-luz/domestico-indexada), puedes consultar la [evolución de los precios hora a hora](https://www.somenergia.coop/es/servicios/tendencia-de-los-precios) porque depende del mercado eléctrico. Si en algún momento decides venir a la cooperativa, podrás cambiar de tarifa siempre que lo necesites.'
    : 'Si quieres, también puedes optar por la [tarifa indexada](https://www.somenergia.coop/es/tarifas-luz/domestico-indexada). Tiene un precio variable que sigue el mercado eléctrico hora a hora. Una vez en la cooperativa, podrás cambiar de tarifa siempre que lo necesites, de forma sencilla. En este artículo te explicamos las [diferencias entre ambas tarifas](https://es.support.somenergia.coop/article/1332-comparacion-de-las-tarifas-por-periodos-y-las-indexadas).'}

Con nosotros tendrás un suministro 100% renovable y te sumarás a una cooperativa sin ánimo de lucro con más de 87.000 personas y entidades socias que impulsan un modelo energético más justo y transparente.

${unfavorable ? '' : 'Para contratar la luz con nosotros, es necesario que te asocies a la cooperativa. La aportación al capital social es de 100 € (una sola vez y retornable si algún día te das de baja). Ser miembro de la cooperativa te permite acceder a [todos estos servicios](https://es.support.somenergia.coop/article/144-cuales-son-las-ventajas-de-ser-socio-a-de-som-energia).\n\n'}[¿Te unes a Som Energia?](https://www.somenergia.coop/es/contrata-la-luz-domestico)

Cuando inicies el [formulario de contratación](https://www.somenergia.coop/es/formulario-contratacion-periodos?form_type=domestic), podrás asociarte y contratar la luz en el mismo proceso. Nosotros nos encargamos de la gestión con tu compañía actual. Te iremos informando del estado del proceso a través de correo electrónico.

💡 Consejo: Para rellenar el formulario cómodamente, ten a mano una factura del punto de suministro que quieres cambiar.

${unfavorable ? 'Por último, si valoras otras comercializadoras, te recomendamos mirar más allá del precio: el coste real de la energía y la potencia (algunas compañías rebajan la parte variable y encarecen la fija), si tiene permanencia, cuánto dura la oferta (durante cuánto tiempo te mantendrá los precios que te ofrecen) y cuáles serán los precios después.\n\nTambién es importante valorar la calidad del servicio y la misión de la empresa con la que tienes la luz contratada. En este sentido, te informamos que Som Energia es [la comercializadora eléctrica mejor valorada por la OCU](https://www.ocu.org/vivienda-y-energia/gas-luz/informe/satisfaccion-proveedores-energia) desde hace años.\n\n' : ''}Si tienes alguna duda, responde este mismo correo y te lo resolvemos.

Atentamente,`,
    }
  }
  const result = savings > 0
    ? 'El resultat és favorable: el cost amb Som Energia és inferior al de la factura actual.'
    : unfavorable
      ? 'El resultat és desfavorable: el cost amb Som Energia és superior al de la factura actual.'
      : 'En aquesta simulació, el cost amb Som Energia és igual al de la factura actual.'
  return {
    intro: `Hola,

Gràcies per aportar-nos les dades del teu consum!

En el document adjunt hi trobaràs la simulació de la teva factura amb la [tarifa períodes de Som Energia](https://www.somenergia.coop/ca/tarifes-llum/domestic-periodes).

${result} A continuació veuràs el resum:`,
    body: `Al document hi trobaràs el detall. Aquesta simulació només és vàlida per a aquesta factura i no és extrapolable al cost anual de la llum.

${unfavorable
    ? 'Pel que fa a l’altra opció que oferim, la [tarifa indexada](https://www.somenergia.coop/ca/tarifes-llum/domestic-indexada/), podràs consultar [l’evolució dels preus hora a hora](https://www.somenergia.coop/ca/servicios/tendencia-dels-preus) per fer-te una idea de la tendència de preus recents. Si contractes la llum amb la cooperativa, podràs canviar de tarifa sempre que ho necessitis.'
    : 'Si vols, també pots optar per la [tarifa indexada](https://www.somenergia.coop/ca/tarifes-llum/domestic-indexada/). Té un preu variable que segueix el mercat elèctric hora a hora. Un cop siguis a la cooperativa, podràs canviar de tarifa sempre que ho necessitis, de manera senzilla. En aquest article t’expliquem les [diferències entre les dues tarifes](https://ca.support.somenergia.coop/article/1331-comparacio-de-les-tarifes-per-periodes-i-indexades).'}

Amb nosaltres tindràs un subministrament 100% renovable i et sumaràs a una cooperativa sense ànim de lucre amb més de 87.000 persones i entitats sòcies que impulsen un model energètic més just i transparent.

${unfavorable ? '' : 'Per contractar la llum amb nosaltres, cal que t’associïs a la cooperativa. L’aportació al capital social és de 100 € (una sola vegada i retornable si algun dia et dones de baixa). Ser membre de la cooperativa et permet accedir a [tots aquests serveis](https://ca.support.somenergia.coop/article/186-quins-son-els-avantatges-de-ser-soci-a-de-som-energia).\n\n'}[Vols unir-te a Som Energia?](https://www.somenergia.coop/ca/contracta-la-llum-domestic)

Quan iniciïs el [formulari de contractació](https://www.somenergia.coop/ca/formulari-contractacio-periodes/?form_type=domestic), podràs ${unfavorable ? 'associar-te i contractar la llum' : 'indicar quina sòcia et convida, associar-te o posar els codis d’algun acord de col·laboració i contractar la llum'} en el mateix procés. Nosaltres ens encarreguem de la gestió amb la teva companyia actual. T’anirem informant de l’estat del procés a través de correu electrònic.

💡 Consell: Per omplir el formulari còmodament, tingues a mà una factura del punt de subministrament que vols canviar.

${unfavorable ? 'Finalment, si valores altres comercialitzadores, et recomanem mirar més enllà del preu: el cost real de l’energia i la potència (algunes companyies rebaixen la part variable i encareixen la fixa), si té permanència, quant dura l’oferta (durant quant de temps et mantindrà els preus que t’ofereixen) i quins seran els preus després.\n\nTambé és important valorar la qualitat del servei i la missió de l’empresa amb qui tens la llum contractada. En aquest sentit, t’informem que Som Energia som [la comercialitzadora elèctrica més ben valorada per l’OCU](https://www.ocu.org/vivienda-y-energia/gas-luz/informe/satisfaccion-proveedores-energia) des de fa anys.\n\n' : ''}Si tens cap dubte, respon aquest mateix correu i te’l resolem.

Atentament,`,
  }
}
