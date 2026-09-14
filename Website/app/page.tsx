import { SiteHeader } from '@/components/site-header'
import { Hero } from '@/components/hero'
import { Statement } from '@/components/statement'
import { FeatureRow } from '@/components/feature-row'
import { PressureHeatmap } from '@/components/pressure-heatmap'
import { AnalyticsPanel } from '@/components/analytics-panel'
import { AlertPanel } from '@/components/alert-panel'
import { UseCases } from '@/components/use-cases'
import { MetricsTable } from '@/components/metrics-table'
import { CallToAction, SiteFooter } from '@/components/site-footer'

export default function Page() {
  return (
    <div className="min-h-screen bg-background">
      <SiteHeader />
      <main>
        <Hero />
        <Statement />

        <FeatureRow
          eyebrow="Sensorer"
          titleLead="Kontinuerlig trykkmåling"
          title="over hele kroppen."
          body="Et tett sensornettverk måler relativt trykk i hundrevis av punkter, flere ganger i sekundet. I stedet for å gjette mellom runder ser personalet nøyaktig hvor belastningen samler seg — korsrygg, hæler, skuldre — og hvordan den endrer seg når pasienten legger seg til rette."
          points={[
            'Hundrevis av trykkpunkter, målt kontinuerlig',
            'Forseglet matte som tåler avtørking og passer eksisterende senger',
            'Ingen bærbare sensorer, ledninger eller forberedelse av pasienten',
            'Fungerer oppå vanlige skum- og luftmadrasser',
          ]}
          visual={<PressureHeatmap />}
        />

        <FeatureRow
          reverse
          eyebrow="Innsikt"
          titleLead="Levende varmekart og analyse"
          title="teamet leser på et blikk."
          body="Rådata om trykk blir til et tydelig bilde: et fargevarmekart ved sengen og trendanalyser over tid. Pleieteamet ser når et område har hatt høyt trykk for lenge, og forstår mønsteret bak et varsel — ikke bare alarmen."
          points={[
            'Varmekart ved sengen med en intuitiv risikofargeskala',
            'Trender over minutter, timer og vakter',
            'Liggetid og terskelsporing per område',
            'Lokalt grensesnitt — ingen skyavhengighet nødvendig',
          ]}
          visual={<AnalyticsPanel />}
        />

        <FeatureRow
          eyebrow="Handling"
          titleLead="Automatiske risikovarsler"
          title="som utløser riktig snuing."
          body="Når trykket holder seg høyt i ett område utover et trygt tidsrom, varsler SmartMat om snuing — rutet til riktig person, på avdelingsskjermen eller en telefon. Det erstatter en stiv klokkestyrt rutine med forebygging drevet av hva som faktisk skjer i sengen."
          points={[
            'Terskel- og liggetidsvarsler, tilpasset hver pasient',
            'Rutet til avdelingsskjermer eller pleiernes telefoner',
            'Snulogging som nullstiller risikotidtakeren automatisk',
            'En tydelig kø så den mest akutte sengen kommer først',
          ]}
          visual={<AlertPanel />}
        />

        <FeatureRow
          reverse
          eyebrow="Holdbarhet"
          titleLead="Bygget for å tåle"
          title="hverdagen på avdelingen."
          body="Pleiemiljøer er krevende: konstant rengjøring, desinfeksjon og tung daglig bruk. SmartMat er utviklet som en helt forseglet matte med lav profil som tåler rutinemessig rengjøring og fortsetter å virke vakt etter vakt."
          points={[
            'Helt forseglet mot væsker og rengjøringsmidler',
            'Lav profil så pasienten knapt merker den',
            'Enkel å ta i bruk — rull ut, koble til og i gang',
            'Personvern innebygd: kun trykkdata, ingen bilder',
          ]}
          visual={
            <img
              src="/mat-detail.png"
              alt="Nærbilde av den forseglede SmartMat trykksensor-matten på en sykehusseng."
              className="w-full rounded-xl object-cover ring-1 ring-border"
            />
          }
        />

        <UseCases />
        <MetricsTable />
        <CallToAction />
      </main>
      <SiteFooter />
    </div>
  )
}
