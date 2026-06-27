% sacjsub.cls
% v1.1 LaTeX class file for submissions to the South African Computer Journal
% (c) 2016 James Dibley <g11d3593@campus.ru.ac.za>
%
% Identification part
\NeedsTeXFormat{LaTeX2e}[1999/12/01]
\ProvidesClass{sacjsub}
    [2017/10/13 v1.1 LaTeX class file for submissions to the South African Computer Journal]


% Initial code
\RequirePackage{kvoptions}
\DeclareStringOption[0]{vol}
\DeclareStringOption[0]{number}
\DeclareStringOption[MONTH OF PUBLICATION]{month}
\DeclareStringOption[\number\year]{year}
\ProcessKeyvalOptions{sacj}
\newcommand{\SACJpagenumber}[1]{\setcounter{page}{#1}}
\newcommand{\@SACJresearcharticle}{Research Article}
\newcommand{\@SACJviewpoint}{Viewpoint}
\newcommand{\@SACJeditorial}{Editorial}
\newcommand{\@SACJcommunication}{Communication}
\newcommand{\@SACJletter}{Letter to the Editor}
\newcommand{\@SACJfrontmatter}{Frontmatter}
\newcommand{\@SACJwebsite}{\url{http://sacj.cs.uct.ac.za}}
\newcommand{\@articletype}{}
\newcommand{\@SACJvolume}{\sacjsub@vol}
\newcommand{\@SACJnumber}{\sacjsub@number}
\newcommand{\@SACJnumberparens}{(\sacjsub@number)}
\newcommand{\@SACJyear}{\sacjsub@year}
\newcommand{\@SACJmonth}{\sacjsub@month}
\newcommand{\@SACJdoi}{DOI TBC}
\newcommand{\@SACJrunningheader}{}
\newcommand{\@sacjcontact}{}
\newcommand{\@SACJ}{\emph{SACJ}}

\author{}
\title{}
\newcounter{@affiliation}
\setcounter{@affiliation}{1}
\renewcommand{\the@affiliation}{\alph{@affiliation}}
\newcommand\@email{}
\newcommand\@authoronly{}
\newcommand\@addresses{}
\newcommand\@theabstract{\@empty}
\newcommand\@thekeywords{}
\newcommand\@thecategories{}
\newcommand\@articlehistory{}
\newcommand\@sacjahrx{}
\newcommand\@sacjahrv{}
\newcommand\@sacjahac{}
\newcommand\@sacjahav{}
\newcommand\@sacjcitationauthors{}
\newcommand{\@SACJnotelist}{}
% \@sacjappendnotelist
% slightly tricky: processes SACJ author affiliation symbols
\newcommand{\@sacjappendnotelist}[2]{%
    \edef#1{%
        \unexpanded\expandafter{#1}%
        \unexpanded{\textsuperscript}%
        \expandafter{\expandafter\unexpanded\expandafter{#2}}%
    }%
}

\newcommand{\@sacjappendcategory}[3]{%
    \def\@thirdarg{#3}
    \def\@emptyhigh{\textbf{}}
    \ifx\@thirdarg\@emptyhigh%
        \edef#1{%
            \unexpanded\expandafter{#1}%
            {~$\bullet$~}%
            \expandafter{\expandafter\unexpanded\expandafter{#2}}%
        }%
    \else%
        \edef#1{%
            \unexpanded\expandafter{#1}%
            {~$\bullet$~}%
            \expandafter{\expandafter\unexpanded\expandafter{#2}}%
            {~$\sim$~}%
            \unexpanded\expandafter{#3}%
        }%
    \fi%
}

\newcommand\@buildtitlefooter{
    \newcommand\@titlefooter{}
    \expandafter\ifx\@articletype\@SACJresearcharticle
    \g@addto@macro\@titlefooter{\footnotesize%
        \hangindent=\parindent{\@sacjcitationauthors~(\sacjsub@year). \@title.~%
        \emph{South African Computer Journal~\@SACJvolume}\@SACJnumberparens,~%
        \thepage--\pageref{LastPage}.~%
        \@SACJdoi}\par%
    }
    \fi
    \expandafter\ifx\@articletype\@SACJviewpoint
    \g@addto@macro\@titlefooter{\footnotesize%
        \hangindent=\parindent{\@sacjcitationauthors~(\sacjsub@year). \@title~[Viewpoint].~%
        \emph{South African Computer Journal~\@SACJvolume},~%
        \thepage--\pageref{LastPage}.~%
        \@SACJdoi}\par%
    }
    \fi
    \expandafter\ifx\@articletype\@SACJletter
    \g@addto@macro\@titlefooter{\footnotesize%
        \hangindent=\parindent{\@sacjcitationauthors~(\sacjsub@year). \@title~[Letter to the Editor].~%
        \emph{South African Computer Journal~\@SACJvolume},~%
        \thepage--\pageref{LastPage}.~%
        \@SACJdoi}\par%
    }
    \fi
    \expandafter\ifx\@articletype\@SACJcommunication
    \g@addto@macro\@titlefooter{\footnotesize%
        \hangindent=\parindent{\@sacjcitationauthors~(\sacjsub@year). \@title~[Communication].~%
        \emph{South African Computer Journal~\@SACJvolume},~%
        \thepage--\pageref{LastPage}.~%
        \@SACJdoi}\par%
    }
    \fi
    \g@addto@macro\@titlefooter{\footnotesize%
        \noindent Copyright \copyright~the author(s);~%
        published under a \protect\href{http://creativecommons.org/licenses/by-nc/4.0/}{Creative Commons NonCommercial 4.0 License (CC BY-NC 4.0)}.\\%
        \emph{SACJ} is a publication of the South African Institute of Computer Scientists and Information Technologists. ISSN 1015-7999 (print) ISSN 2313-7835 (online).%
    }
}

\newcommand{\@buildarticlehistory}{%
    \g@addto@macro\@articlehistory{\par}
    \ifx\@sacjahrx\empty\else
        \g@addto@macro\@articlehistory{Received: \@sacjahrx\newline}
      \fi
      \expandafter \ifx\@sacjahrv\empty\else
         \g@addto@macro\@articlehistory{Revised: \@sacjahrv\newline}
      \fi
      \ifx\@sacjahac\empty\else
        \g@addto@macro\@articlehistory{Accepted: \@sacjahac\newline}
      \fi
      \ifx\@sacjahav\empty\else
        \g@addto@macro\@articlehistory{Available online: \@sacjahav}
      \fi
}

\newcommand\@SACJmaketitle{%
    \@buildtitlefooter
    \expandafter\ifx\@articletype\@SACJresearcharticle
    \@buildarticlehistory
    \fi
    \newpage
    \setlength{\parindent}{0pt}
    \renewcommand{\baselinestretch}{1.1}\normalsize
    {\raggedright \Huge\textsf{\@title}\par}
    \renewcommand{\baselinestretch}{1}\normalsize
    \ifx\@author\@empty\else
        \vskip 1em
        {%
            \expandafter\ifx\@articletype\@SACJresearcharticle
                \normalsize \textsf{\@author}
            \else
                \normalsize \textsf{\@email}
            \fi
            \par
        }
    \fi
    \ifx\@addresses\@empty\else
        {\footnotesize\medskip\textsf{\@addresses}}
    \fi
    \expandafter\ifx\@articletype\@SACJresearcharticle
        \rule{\textwidth}{.2pt}\par
        \if\@theabstract\@empty\else
            \vspace{0.2em}
            \footnotesize\textsf{\bfseries{\uppercase{Abstract}}}\\
            % Relax parindent for abstracts that might need >1 paragraph
            \setlength{\parindent}{20pt}
            {\footnotesize \@theabstract}\par
            \setlength{\parindent}{0pt}
            \vspace{0.5\baselineskip}
            \footnotesize \textsf{\bfseries{Keywords:}} \@thekeywords\par
            \vspace{0.5\baselineskip}
            % Set the next section in \raggedright because the ACM 2012
            % categories get quite wildly spaced across the page otherwise
            { \raggedright
            \footnotesize \textsf{\bfseries{Categories:}} \scriptsize \@thecategories\par
            }
            \vspace{0.5\baselineskip}
            \begin{tabular}{@{}p{.625\linewidth} p{.375\linewidth}@{}}
            \footnotesize \textsf{\bfseries{Email}}:\newline\scriptsize \@email &%
            \footnotesize \textsf{\bfseries{Article history}}: \scriptsize\@articlehistory
            \end{tabular}
            \rule{\textwidth}{0.2pt}\par
        \fi
    \else
        \vspace{0.5\baselineskip}
        \rule{\textwidth}{0.2pt}\par
    \fi
    \ifx\@titlefooter\@empty\else
        \protected@xdef\@thanks{\protect\footnotetext{\hspace{-1.85em}\@titlefooter}}%
    \fi
    \hypersetup{%
        pdfauthor={\@authoronly},%
        pdftitle={\@title},%
        pdfkeywords={\@thekeywords}%
    }
}

% Declaration of options
\DeclareOption{final}{%
    \renewcommand{\@SACJvolume}{\sacjsub@vol}%
    \renewcommand{\@SACJnumber}{\sacjsub@number}%
    \renewcommand{\@SACJnumberparens}{(\sacjsub@number)}%
    \renewcommand{\@articletype}{\@SACJresearcharticle}%
    }
\DeclareOption{submission}{%
    \renewcommand{\@SACJvolume}{Vol TBC}%
    \renewcommand{\@SACJnumber}{Num TBC}%
    \renewcommand{\@SACJnumberparens}{(Num TBC)}%
    \renewcommand{\@articletype}{\@SACJresearcharticle}%
    }
\DeclareOption{communication}{\renewcommand{\@articletype}{\@SACJcommunication}}
\DeclareOption{letter}{\renewcommand{\@articletype}{\@SACJletter}}
\DeclareOption{erratum}{\renewcommand{\@articletype}{Erratum}}
\DeclareOption{viewpoint}{\renewcommand{\@articletype}{\@SACJviewpoint}}
\DeclareOption{includenumbers}{\includenumberstrue}
\DeclareOption*{\typeout{Unknown option `\CurrentOption'}}

% Execution of options
\ProcessOptions\relax

% Package loading
\LoadClass[a4paper,12pt]{article}
\renewcommand{\footnoterule}{}
\RequirePackage[a4paper,total={495pt,600pt},headheight=75pt,centering]{geometry}
\RequirePackage{fancyhdr}
\RequirePackage{lastpage}
\RequirePackage{sectsty}
\RequirePackage{microtype}
\RequirePackage{titlesec}
\RequirePackage{csquotes}
\RequirePackage{multirow}
\RequirePackage[pdftex]{graphicx}
\RequirePackage[font=small]{caption}
\RequirePackage[square,numbers]{natbib}
\PassOptionsToPackage{hyphens}{url}\usepackage[colorlinks=true,citecolor=black,filecolor=blue,urlcolor=blue]{hyperref}

% Special commands for package and class files
\fancypagestyle{firstpage}{%
    \fancyhf{}
    \expandafter\ifx\@articletype\@SACJfrontmatter
        \fancyhead[C]{%
            {\textsf{\Huge South African Computer Journal}}
         }
    \else
        \fancyhead[R]{\footnotesize%
            \textsf{%
            \emph{SACJ} \@SACJvolume\@SACJnumberparens~\@SACJmonth~\@SACJyear \\
            \@articletype%
            }%
        }
        \renewcommand{\footrulewidth}{0pt}
    \fi
    \renewcommand{\headrulewidth}{0pt}
}
\fancypagestyle{followingpage}{%
    \fancyhf{}
    \expandafter\ifx\@articletype\@SACJfrontmatter
        \renewcommand{\headrulewidth}{0pt}
        \fancyhead[C]{%
            {\textsf{\Huge South African Computer Journal}}
         }
         \renewcommand{\footrulewidth}{0.5pt}
    \else
        \fancyhead[L]{\footnotesize \@SACJrunningheader}
        \fancyhead[R]{%
            \textsf{\footnotesize%
            \thepage
            }
        }
        \expandafter\ifx\@articletype\@SACJresearcharticle
        \fancyfoot[R]{%
            \footnotesize \textsf{\@SACJdoi}
        }
        \fi
        \expandafter\ifx\@articletype\@SACJviewpoint
        \fancyfoot[R]{%
            \footnotesize \textsf{\@SACJdoi}
        }
        \fi
        \expandafter\ifx\@articletype\@SACJletter
        \fancyfoot[R]{%
            \footnotesize \textsf{\@SACJdoi}
        }
        \fi
        \expandafter\ifx\@articletype\@SACJcommunication
        \fancyfoot[R]{%
            \footnotesize \textsf{\@SACJdoi}
        }
        \fi
        \renewcommand{\headrulewidth}{0.5pt}
    \fi
}

% Special class file commands
\allsectionsfont{\sffamily\raggedright} % prevent odd spacing
\urlstyle{sf} % typewriter style is frankly harder to read
\pagestyle{followingpage}
\AtBeginDocument{\thispagestyle{firstpage}}
\AtBeginDocument{%
    \expandafter\ifx\@articletype\@SACJeditorial
        \pagenumbering{roman}
    \fi
    \expandafter\ifx\@articletype\@SACJfrontmatter
        \pagenumbering{roman}
    \fi
}

\newcommand{\SACJdoi}[1]{\renewcommand{\@SACJdoi}{\url{#1}}}
\newcommand{\SACJtitle}[1]{\renewcommand\@title{#1}}
\newcommand{\SACJaddress}[2][default]{%
    \expandafter\ifx\csname @SACJnote#1\endcsname\relax%
        \g@addto@macro\@addresses{#2\par}%
    \else%
        \g@addto@macro\@addresses{\textsuperscript{%
            \csname @SACJnote#1\endcsname}\space#2\par}%
    \fi%
}

\let\@maketitle\@SACJmaketitle

\newcommand\SACJmaketitle{%
    \par
    \typeout{Processing paper ``\@title''.}
    \begingroup
        \renewcommand\thefootnote{\@fnsymbol\c@footnote}%
        \newpage
        \global\@topnum\z@     % prevents figures from going at top of page
        \@maketitle
        \@thanks
    \endgroup
        \setcounter{footnote}{0}%
        \global\let\thanks\relax
        \global\let\@maketitle\relax
        \global\let\@thanks\@empty
        \global\let\@date\@empty
        \global\let\title\relax
        \global\let\@title\@empty
        \global\let\author\relax
        \global\let\@author\@empty
        \global\let\@authoronly\@empty
        \global\let\@addresses\@empty
        \global\let\@email\@empty
        \global\let\@theabstract\@empty
        \global\let\@thekeywords\@empty
        \global\let\@thecategories\@empty
        \global\let\date\relax
        \global\let\and\relax
}

\newcommand{\SACJauthor}[4][default]{%
    \renewcommand{\@SACJnotelist}{\empty}
    \def\@testforx{default}
    \def\@firstarg{#1}
    \ifx\@firstarg\@testforx%
        \edef\@@note{}%
    \else
    \def\@corresponding{#4}
        \@for\next:=#1\do{%
            \expandafter\ifx\@SACJnotelist\empty\else
                \@sacjappendnotelist{\@SACJnotelist}{,\space}
            \fi
            \expandafter\ifx\csname @SACJnote\next\endcsname\relax
                \edef\@@note{\the@affiliation}%
                \expandafter\edef\csname @SACJnote\next \endcsname{\@@note}%
                \@sacjappendnotelist{\@SACJnotelist}{\@@note}
                \stepcounter{@affiliation}
            \else
                \@sacjappendnotelist{\@SACJnotelist}{\csname @SACJnote\next \endcsname}
            \fi
        }
    \fi
    \ifx\@author\@empty\else
        \g@addto@macro\@author{, }%
        \g@addto@macro\@authoronly{, }%
    \fi
    \def\@thirdarg{#3}
    \expandafter\ifx\@thirdarg\@empty\else
        \expandafter\ifx\@email\newline\else
            \g@addto@macro\@email{, }%
            \g@addto@macro\@email\newline%
        \fi
        \g@addto@macro\@email{#2 %
            \protect\href{mailto:#3}{\nolinkurl{#3}}}%
        \expandafter\ifx\@corresponding\@empty\else
            \g@addto@macro\@email{\space{\tiny\textsf{(CORRESPONDING)}}}%
        \fi
    \fi%
    \g@addto@macro\@author{#2}%
    \@sacjappendnotelist{\@author}{\@SACJnotelist}
    \g@addto@macro\@authoronly{#2}%
}

\newcommand\SACJappendextraemail[2]{%
    \def\@corresponding{#2}%
    \g@addto@macro\@email{,\space}%
    \g@addto@macro\@email{%
        \protect\href{mailto:#1}{\nolinkurl{#1}}}%
    \expandafter\ifx\@corresponding\@empty\else
        \g@addto@macro\@email{\space{\tiny\textsf{(CORRESPONDING)}}}%
    \fi
}

\newcommand\SACJACMCategory[3]{%
    \def\@priority{#3}%
    \def\@highpriority{h}%
    \def\@medpriority{m}%
    \def\@lowpriority{l}%
    \ifx\@priority\@highpriority%
        \@sacjappendcategory{\@thecategories}{\textbf{#1}}{\textbf{#2}}%
    \fi%
    \ifx\@priority\@medpriority%
        \@sacjappendcategory{\@thecategories}{\textit{#1}}{\textit{#2}}%
    \fi%
    \ifx\@priority\@lowpriority%
        \@sacjappendcategory{\@thecategories}{#1}{#2}%
    \fi%
}

\newcommand\SACJabstract[1]{\renewcommand\@theabstract{#1}}
\newcommand\SACJkeywords[1]{\renewcommand\@thekeywords{#1}}
\newcommand\SACJcategories[1]{\renewcommand\@thecategories{#1}}

\newcommand\SACJAHReceived[1]{\renewcommand{\@sacjahrx}{\textsf{#1}}}
\newcommand\SACJAHReceivedRevised[1]{\renewcommand{\@sacjahrv}{\textsf{#1}}}
\newcommand\SACJAHAccepted[1]{\renewcommand{\@sacjahac}{\textsf{#1}}}
\newcommand\SACJAHAvailableOnline[1]{\renewcommand{\@sacjahav}{\textsf{#1}}}

\newcommand\SACJrunningheader[2]{\renewcommand{\@SACJrunningheader}%
    {\textsf{\textbf{#1}: #2}}}

\newcommand\SACJcitationauthors[1]{\renewcommand\@sacjcitationauthors{#1}}

% Sectioning
\renewcommand\section{\@startsection {section}{1}{\z@}%
                                   {-3.5ex \@plus -1ex \@minus -.2ex}%
                                   {2.3ex \@plus.2ex}%
                                   {\large\sffamily\uppercase}}
\renewcommand\subsection{\@startsection{subsection}{2}{\z@}%
                                     {-3.25ex\@plus -1ex \@minus -.2ex}%
                                     {0.9ex \@plus .2ex}%
                                     {\flushleft\normalfont\sffamily\large}}
\renewcommand\subsubsection{\@startsection{subsubsection}{3}{\z@}%
                                     {-3.25ex\@plus -1ex \@minus -.2ex}%
                                     {0.9ex \@plus .2ex}%
                                     {\normalfont\normalsize\sffamily}}
\newcommand\subsubsubsection{\@startsection{subsubsection}{4}{\z@}%
                                     {-3.25ex\@plus -1ex \@minus -.2ex}%
                                     {0.9ex \@plus .2ex}%
                                     {\normalfont\normalsize\sffamily}}

\newcommand{\SACJfourthlevel}{
    \setcounter{secnumdepth}{4}
    \titleformat{\section}
    {\large\sffamily\uppercase}{\thesection}{1em}{}
    \titlespacing*{\section}
    {0pt}{3.25ex plus 1ex minus .2ex}{2.3ex plus .2ex}
    \titleformat{\paragraph}
    {\normalfont\normalsize\sffamily}{\theparagraph}{1em}{}
    \titlespacing*{\paragraph}
    {0pt}{3.25ex plus 1ex minus .2ex}{1.5ex plus .2ex}
}
