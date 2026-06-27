%%
%% sacjsub.cls  --  WORKING STUB for Overleaf compilation
%%
%% PURPOSE: Lets trisecure_sacj.tex compile immediately while you
%%          obtain the official SACJ class file.
%%
%% TO REPLACE WITH THE OFFICIAL FILE (recommended before final submission):
%%   1. Visit: https://journals.assaf.org.za/index.php/sacj/about/submissions
%%   2. Download the "Complete LaTeX example" archive
%%   3. Extract sacjsub.cls from that archive
%%   4. Upload it to this Overleaf project, replacing this stub file
%%
%% This stub defines all SACJ-specific commands and produces valid,
%% readable single-column output for review preparation.
%% The real sacjsub.cls may produce slightly different cosmetic layout.
%%

\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{sacjsub}[2026/06/27 SACJ Submission Stub Class v1.0]

%% -- Options -------------------------------------------------
%% Absorb the 'submission' option silently; pass others to article
\DeclareOption{submission}{}
\DeclareOption*{\PassOptionsToClass{\CurrentOption}{article}}
\ProcessOptions\relax

%% -- Base class ----------------------------------------------
\LoadClass[a4paper,12pt]{article}

%% -- Required packages ---------------------------------------
\RequirePackage[top=2.5cm,bottom=2.5cm,left=3cm,right=3cm]{geometry}
\RequirePackage{natbib}       % numeric [n] citations via unsrtnat
\RequirePackage{fancyhdr}     % running headers
\RequirePackage{etoolbox}     % \appto, \ifdefempty
\RequirePackage{xcolor}       % \textcolor used in title-page stub note
\setlength{\headheight}{14pt} % prevent fancyhdr underfull-head warning

%% ============================================================
%% Internal storage macros (all start empty)
%% ============================================================
\newcommand{\SACJ@title}{}
\newcommand{\SACJ@abstract}{}
\newcommand{\SACJ@keywords}{}
\newcommand{\SACJ@cite}{}
\newcommand{\SACJ@runA}{}
\newcommand{\SACJ@runB}{}
\newcommand{\SACJ@acm}{}
\newcommand{\SACJ@authors}{}
\newcommand{\SACJ@addrs}{}

%% ============================================================
%% User-facing SACJ commands
%% ============================================================

%% \SACJtitle{Full title of the paper}
\newcommand{\SACJtitle}[1]{%
  \renewcommand{\SACJ@title}{#1}}

%% \SACJauthor[affcode]{Name}{email}{corresponding or empty}
%% In blind review submission these lines are commented out.
%% Define the command so it compiles when uncommented.
\newcommand{\SACJauthor}[4][]{%
  \appto\SACJ@authors{%
    \par\noindent #2%
    \ifblank{#3}{}{\ \texttt{<#3>}}%
    \ifblank{#4}{}{\ (\textit{#4})}%
  }%
}

%% \SACJappendextraemail{email}{flag}
%% For authors who need a second email address listed.
\newcommand{\SACJappendextraemail}[2]{%
  \appto\SACJ@authors{;\ \texttt{<#1>}}}

%% \SACJaddress[affcode]{Institution and address}
\newcommand{\SACJaddress}[2][]{%
  \appto\SACJ@addrs{\par\noindent\textit{#2}}}

%% \SACJrunningheader{Short author list}{Short title}
\newcommand{\SACJrunningheader}[2]{%
  \renewcommand{\SACJ@runA}{#1}%
  \renewcommand{\SACJ@runB}{#2}}

%% \SACJcitationauthors{Full APA-style author list}
%% Appears at foot of title page as the citation line.
\newcommand{\SACJcitationauthors}[1]{%
  \renewcommand{\SACJ@cite}{#1}}

%% \SACJabstract{Abstract text}
%% Must be fewer than 200 words; no references, footnotes, or
%% special symbols hard to render in plain text (SACJ requirement).
\newcommand{\SACJabstract}[1]{%
  \renewcommand{\SACJ@abstract}{#1}}

%% \SACJACMCategory{Top level}{Sub-category}{h/m/l relevance}
%% Use ACM CCS 2012 only: https://dl.acm.org/ccs/ccs.cfm
%% Relevance: h = highly relevant, m = moderate, l = low
\newcommand{\SACJACMCategory}[3]{%
  \appto\SACJ@acm{%
    \item \textit{#1}~$\to$~#2%
    \ifblank{#3}{}{%
      \if h#3~(highly relevant)\else
      \if m#3~(moderately relevant)\else
      ~(low relevance)\fi\fi}%
  }%
}

%% \SACJkeywords{comma-separated keyword list}
\newcommand{\SACJkeywords}[1]{%
  \renewcommand{\SACJ@keywords}{#1}}

%% ============================================================
%% \SACJmaketitle
%% Generates the complete title page. Call this INSIDE
%% \begin{document}, immediately before \section{Introduction}.
%% ============================================================
\newcommand{\SACJmaketitle}{%
  \thispagestyle{empty}%
  %
  %% --- Title block ---
  \begin{center}
    \vspace*{0.8cm}
    {\LARGE\bfseries \SACJ@title \par}
    \vspace{1.2em}
    %
    %% Show author block if present; otherwise show blind-review notice
    \ifdefempty{\SACJ@authors}{%
      {\small\itshape
        [Author details omitted for double-blind review.
         All authors have been listed on the journal submission form.]}%
    }{%
      \SACJ@authors \par
      \vspace{0.4em}
      \SACJ@addrs \par
    }%
    \vspace{1.2em}
  \end{center}
  %
  %% --- Abstract ---
  \noindent\rule{\linewidth}{0.6pt}\par
  \vspace{0.3em}
  \noindent{\small\bfseries Abstract.}\enspace
  {\small \SACJ@abstract}
  \vspace{0.3em}\par
  \noindent\rule{\linewidth}{0.6pt}\par
  \vspace{0.5em}
  %
  %% --- Keywords ---
  \ifdefempty{\SACJ@keywords}{}{%
    \noindent{\small\bfseries Keywords:}\enspace
    {\small \SACJ@keywords}\par
    \vspace{0.4em}
  }%
  %
  %% --- ACM CCS 2012 categories ---
  \ifdefempty{\SACJ@acm}{}{%
    \noindent{\small\bfseries ACM Computing Classification System (2012):}
    \begin{itemize}
      \small\itemsep 0pt\parsep 0pt
      \SACJ@acm
    \end{itemize}
    \vspace{0.2em}
  }%
  %
  %% --- Citation line at foot of title page ---
  \ifdefempty{\SACJ@cite}{}{%
    \vfill
    \noindent\rule{\linewidth}{0.4pt}\par
    \noindent{\footnotesize
      \textit{Cite as:}\ \SACJ@cite\
      \SACJ@title.
      \textit{South African Computer Journal}.}\par
    \noindent{\footnotesize\textcolor{gray}{%
      [This PDF was produced with a stub sacjsub.cls.
       Replace with the official class before final submission.]}}%
  }%
  %
  \newpage
  %
  %% --- Running headers for pages 2+ ---
  \pagestyle{fancy}
  \fancyhf{}
  \fancyhead[L]{\footnotesize\itshape \SACJ@runA}
  \fancyhead[C]{\footnotesize\itshape \SACJ@runB}
  \fancyfoot[C]{\footnotesize\thepage}
  \renewcommand{\headrulewidth}{0.4pt}
  \setcounter{page}{1}%
}

%% ============================================================
%% Miscellaneous style tweaks to approximate SACJ single-column
%% ============================================================

%% Paragraph spacing (SACJ uses block paragraphs, no indent)
\setlength{\parskip}{6pt}
\setlength{\parindent}{0pt}

%% Section heading style (approximate SACJ look)
\makeatletter
\renewcommand\section{\@startsection{section}{1}{\z@}%
  {-14pt \@plus -4pt \@minus -2pt}{6pt \@plus 2pt}%
  {\normalfont\large\bfseries\MakeUppercase}}
\renewcommand\subsection{\@startsection{subsection}{2}{\z@}%
  {-10pt \@plus -3pt}{4pt \@plus 2pt}%
  {\normalfont\normalsize\bfseries}}
\renewcommand\subsubsection{\@startsection{subsubsection}{3}{\z@}%
  {-8pt \@plus -2pt}{3pt}%
  {\normalfont\normalsize\itshape}}
\makeatother

%% Float placement defaults
\setcounter{topnumber}{4}
\setcounter{bottomnumber}{3}
\setcounter{totalnumber}{6}
\renewcommand{\topfraction}{0.90}
\renewcommand{\textfraction}{0.07}

%% xcolor is loaded near the top of this file via \RequirePackage{xcolor}
