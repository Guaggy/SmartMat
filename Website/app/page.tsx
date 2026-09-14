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
          title="i setet."
          body="Et tett sensornettverk måler trykket i setet, i lår og i de områdene som får mest belastning under bruk. I stedet for å gjette mellom justeringer ser brukeren eller personalet hvor kraften samler seg og hvordan den endrer seg når stolen justeres."
          points={[
            'Hundrevis av trykkpunkter, målt kontinuerlig',
            'Forseglet sensorpanel tilpasset stol og rullestol',
            'Ingen ekstra utstyr eller klumpete tilkoblinger',
            'Fungerer i en vanlig daglig bruk med enkel justering',
          ]}
          visual={<PressureHeatmap />}
        />

        <FeatureRow
          reverse
          eyebrow="Innsikt"
          titleLead="Levende varmekart og analyse"
          title="som er lett å lese."
          body="Rådata om trykk blir til et tydelig bilde av setet og de områdene som får mest belastning. Brukeren eller personalet ser når et område har vært under høyt trykk for lenge, og forstår mønsteret bak en advarsel i stedet for bare en alarm."
          points={[
            'Varmekart av setet med enkel risikofargeskala',
            'Trender over minutter og timer',
            'Trykk og belastningssporing per område',
            'Lokalt grensesnitt uten behov for skytilkobling',
          ]}
          visual={<AnalyticsPanel />}
        />

        <FeatureRow
          eyebrow="Handling"
          titleLead="Automatiske risikovarsler"
          title="som styrer riktig justering."
          body="Når trykket holder seg høyt i ett område over en trygg tidsgrense, varsler Verdia Stol brukeren eller personalet om justering. Det erstatter en rigid rutine med en mer proaktiv oppfølging av det som faktisk skjer i setet."
          points={[
            'Terskel- og belastningsvarsler, tilpasset brukeren',
            'Rutet til skjerm eller telefon i samme arbeidsflyt',
            'Logg for justeringer og belastningshistorikk',
            'Tydelig prioritering av de mest kritiske setepunktene',
          ]}
          visual={<AlertPanel />}
        />

        <FeatureRow
          reverse
          eyebrow="Holdbarhet"
          titleLead="Bygget for hverdagens bruk"
          title="i en stol eller rullestol."
          body="Bruk i hverdagen krever enkelhet, hygiene og robusthet. Verdia Stol er utviklet som et tett, forseglet sensorelement som tåler rengjøring, daglig bruk og stadig tilpasning i arbeid med brukeren."
          points={[
            'Helt forseglet mot væsker og rengjøring',
            'Lav profil uten å påvirke komforten',
            'Enkel å ta i bruk i eksisterende oppsett',
            'Personvern innebygd: kun trykkdata, ingen bilder',
          ]}
          visual={
            <img
              src="/mat-detail.png"
              alt="Nærbilde av den forseglede Verdia Stol sensorplaten i en stol."
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
