import { Helmet } from 'react-helmet-async'

interface Props {
  title: string
  description?: string
}

export function PageTitle({ title, description }: Props) {
  return (
    <Helmet>
      <title>{title} — PaperTranslate</title>
      {description && <meta name="description" content={description} />}
      <meta property="og:title" content={`${title} — PaperTranslate`} />
      {description && <meta property="og:description" content={description} />}
    </Helmet>
  )
}
